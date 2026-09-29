"""TTS engine abstraction for the VoxForge self-hosted voice path.

Two interchangeable engines, selected automatically at startup:

* ``SayEngine``   – macOS only. Wraps the built-in, on-device ``say`` command.
                    Needs no model download and returns real WAV files, so the
                    "downloadable voice" works out of the box on a Mac.
* ``PiperEngine`` – cross-platform. Shells out to a self-hosted Piper binary
                    + ``.onnx`` voice model (see setup.sh). Used when a model is
                    present, matching the engine recommended in the PRD/TRD.

Neither engine calls a third-party API. No user text is persisted.
"""

from __future__ import annotations

import json

import emotion as emotion_mod
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

# Serializes the torch-based engines (Piper/MMS/Parler) — torch model inference
# is not safe to run concurrently. Kokoro (onnxruntime) and macOS `say` are
# thread-safe and intentionally do NOT use this, so they never block on it.
_TORCH_LOCK = threading.Lock()

MODELS_DIR = Path(__file__).parent / "models"


@dataclass
class VoiceInfo:
    id: str
    name: str
    lang: str
    gender: str = "neutral"


class EngineError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


_TORCH_CONFIGURED = False


def _configure_torch() -> None:
    """Tune PyTorch CPU threading once, for faster inference.

    Compute-bound transformer inference is fastest using the *physical* core
    count — using all logical (hyperthreaded) cores causes contention and is
    slower. Also pin inter-op threads to 1 (single request at a time).
    """
    global _TORCH_CONFIGURED
    if _TORCH_CONFIGURED:
        return
    try:
        import torch
    except ImportError:
        return
    phys = None
    if platform.system() == "Darwin":
        try:
            phys = int(
                subprocess.run(
                    ["sysctl", "-n", "hw.physicalcpu"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
        except Exception:
            phys = None
    n = phys or max(1, (os.cpu_count() or 2) // 2)
    torch.set_num_threads(n)
    try:
        torch.set_num_interop_threads(1)
    except Exception:
        pass  # can only be set once, before any parallel work
    _TORCH_CONFIGURED = True


_TORCH_DEVICE: str | None = None


def torch_device() -> str:
    """Pick the best torch device once: CUDA (AWS GPU) > Apple MPS > CPU.
    Override with VOXFORGE_DEVICE=cpu|cuda|mps. On GPU this makes Parler/MMS
    run in ~1-3s instead of ~70s on CPU — no code change needed at deploy."""
    global _TORCH_DEVICE
    if _TORCH_DEVICE is not None:
        return _TORCH_DEVICE
    forced = os.environ.get("VOXFORGE_DEVICE", "").lower()
    dev = "cpu"
    try:
        import torch

        if forced in ("cpu", "cuda", "mps"):
            dev = forced
        elif torch.cuda.is_available():
            dev = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            dev = "mps"
    except ImportError:
        pass
    _TORCH_DEVICE = dev
    return dev


def _maybe_quantize(model):
    """Dynamic INT8 quantization of Linear layers — the biggest safe CPU
    speedup for transformer inference (~1.3-1.8x), no calibration needed.

    Guarded: if it fails for any reason, returns the original model unchanged,
    so synthesis never errors. Disable with VOXFORGE_QUANTIZE=0.
    """
    # Default OFF: on CPUs without INT8 acceleration (no AVX512-VNNI, e.g. this
    # Intel Mac) dynamic quant is actually SLOWER. Enable only on capable CPUs.
    if os.environ.get("VOXFORGE_QUANTIZE", "0") != "1":
        return model
    try:
        import torch

        q = torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8
        )
        return q.eval()
    except Exception:
        return model


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _polish_wav(
    path: str,
    target_rms: float = 0.16,  # louder, consistent output level (QA #9)
    peak_ceiling: float = 0.97,
    max_silence: float = 0.30,
    fade_ms: float = 8.0,
) -> None:
    """Studio-polish an engine's raw WAV in place so every voice is clean and
    consistent:

    1. **DC removal** — subtract any DC offset for a clean baseline.
    2. **Trim + cap silences** — strip dead air at the ends and shorten long
       internal gaps to `max_silence` (kills Piper's buffering-like pauses).
    3. **Loudness match** — normalize to a constant `target_rms` measured on
       *voiced* speech only, so switching voices doesn't change the volume.
    4. **Peak safety** — scale down if the result would exceed `peak_ceiling`,
       so loudness matching never causes clipping.
    5. **De-click fades** — short fade in/out removes the pop at clip edges.

    No-ops gracefully if numpy is unavailable.
    """
    try:
        import wave

        import numpy as np
    except ImportError:
        return

    try:
        with wave.open(path, "rb") as w:
            sr = w.getframerate()
            ch = w.getnchannels()
            sw = w.getsampwidth()
            n = w.getnframes()
            raw = w.readframes(n)
        if sw != 2 or ch != 1 or n == 0:
            return  # only handle 16-bit mono (what our engines emit)

        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        # 1. DC removal.
        x = x - float(np.mean(x))

        # 2. Frame energies -> voiced mask (drives both silence cap + loudness).
        win = max(1, int(0.02 * sr))
        nf = len(x) // win
        voiced_rms = None
        if nf > 1:
            frames = x[: nf * win].reshape(nf, win)
            energy = np.sqrt(np.mean(frames**2, axis=1))
            thr = max(0.01, 0.03 * float(energy.max()))
            voiced = energy > thr
            if voiced.any():
                voiced_rms = float(np.sqrt(np.mean((energy[voiced]) ** 2)))

            # Trim leading/trailing silence, then cap internal gaps.
            cap = max(1, int(max_silence / 0.02))
            keep = np.ones(nf, dtype=bool)
            first = int(np.argmax(voiced)) if voiced.any() else 0
            last = nf - 1 - int(np.argmax(voiced[::-1])) if voiced.any() else nf - 1
            edge = max(1, int(0.06 / 0.02))  # leave ~60ms padding at the ends
            keep[: max(0, first - edge)] = False
            keep[min(nf, last + 1 + edge) :] = False
            i = first
            while i <= last:
                if not voiced[i]:
                    j = i
                    while j <= last and not voiced[j]:
                        j += 1
                    if (j - i) > cap:
                        keep[i + cap : j] = False
                    i = j
                else:
                    i += 1
            mask = np.repeat(keep, win)
            tail = len(x) - len(mask)
            if tail > 0:
                mask = np.concatenate([mask, np.ones(tail, dtype=bool)])
            x = x[mask]

        if len(x) == 0:
            return

        # 3. Loudness match to a constant target (voiced RMS if we have it).
        rms = voiced_rms or float(np.sqrt(np.mean(x**2)))
        if rms > 1e-6:
            x = x * (target_rms / rms)

        # 4. Peak safety so loudness matching never clips.
        peak = float(np.max(np.abs(x)))
        if peak > peak_ceiling:
            x = x * (peak_ceiling / peak)

        # 5. De-click fades at the very start/end.
        f = min(int(fade_ms / 1000 * sr), len(x) // 2)
        if f > 1:
            ramp = np.linspace(0.0, 1.0, f, dtype=np.float32)
            x[:f] *= ramp
            x[-f:] *= ramp[::-1]

        out = np.clip(x * 32768.0, -32768, 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(out.tobytes())
    except Exception:
        # Polishing is best-effort; never fail synthesis over it.
        return


def _atempo_chain(t: float) -> list[float]:
    """Split a tempo factor into a chain each within ffmpeg's atempo [0.5, 2]."""
    t = max(0.25, min(4.0, t))
    out: list[float] = []
    while t > 2.0:
        out.append(2.0)
        t /= 2.0
    while t < 0.5:
        out.append(0.5)
        t /= 0.5
    if abs(t - 1.0) > 1e-3:
        out.append(t)
    return out


def _apply_prosody(
    path: str, *, speed: float = 1.0, pitch: float = 1.0, volume: float = 1.0
) -> None:
    """Apply pitch shift, speed and volume to a WAV in place via ffmpeg, so the
    studio sliders work on EVERY engine (most engines have no native pitch, and
    the loudness polish above erases volume). No-ops when all are default."""
    speed = _clamp(speed, 0.5, 2.0)
    pitch = _clamp(pitch, 0.5, 2.0)
    volume = _clamp(volume, 0.0, 2.0)
    if (
        abs(speed - 1.0) < 1e-3
        and abs(pitch - 1.0) < 1e-3
        and abs(volume - 1.0) < 1e-3
    ):
        return
    if not _has_ffmpeg():
        return
    try:
        import wave

        with wave.open(path, "rb") as w:
            sr = w.getframerate()

        filters: list[str] = []
        # Pitch shift: resample up/down then restore the sample rate. This also
        # changes tempo by `pitch`, which the atempo below compensates for.
        if abs(pitch - 1.0) > 1e-3:
            filters.append(f"asetrate={int(round(sr * pitch))}")
            filters.append(f"aresample={sr}")
        net_tempo = speed / (pitch if abs(pitch - 1.0) > 1e-3 else 1.0)
        for f in _atempo_chain(net_tempo):
            filters.append(f"atempo={f:.4f}")
        if abs(volume - 1.0) > 1e-3:
            filters.append(f"volume={volume:.3f}")
            if volume > 1.0:
                filters.append("alimiter=limit=0.97")
        if not filters:
            return

        out = path + ".pp.wav"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-af", ",".join(filters), out],
            capture_output=True,
        )
        if proc.returncode == 0 and os.path.exists(out):
            os.replace(out, path)
        elif os.path.exists(out):
            os.unlink(out)
    except Exception:
        return  # best-effort; never fail synthesis over prosody


def _finalize(
    wav_path: str,
    fmt: str,
    *,
    speed: float = 1.0,
    pitch: float = 1.0,
    volume: float = 1.0,
) -> tuple[bytes, str]:
    """Polish the WAV, apply prosody (pitch/speed/volume), then return audio
    bytes in the requested format."""
    _polish_wav(wav_path)
    _apply_prosody(wav_path, speed=speed, pitch=pitch, volume=volume)
    if fmt == "mp3":
        try:
            return _wav_to_mp3(wav_path), "audio/mpeg"
        except EngineError:
            pass  # ffmpeg missing -> fall through to WAV
    return Path(wav_path).read_bytes(), "audio/wav"


def _wav_to_mp3(wav_path: str) -> bytes:
    """Best-effort WAV->MP3 via ffmpeg. Raises if ffmpeg is unavailable."""
    if not _has_ffmpeg():
        raise EngineError("ffmpeg-not-available")
    out = wav_path + ".mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", out],
        check=True,
        capture_output=True,
    )
    data = Path(out).read_bytes()
    os.unlink(out)
    return data


# Names commonly associated with a gender, for the picker's filter chips.
_FEMALE = re.compile(
    r"samantha|victoria|karen|moira|tessa|fiona|allison|ava|susan|kate|"
    r"zoe|nora|amelie|amélie|anna|alice|alva|amira|female",
    re.I,
)
_MALE = re.compile(
    r"daniel|alex|fred|tom|david|oliver|rishi|aaron|diego|jorge|luca|"
    r"thomas|gordon|albert|male|reed|eddy",
    re.I,
)


def _guess_gender(name: str) -> str:
    if _FEMALE.search(name):
        return "female"
    if _MALE.search(name):
        return "male"
    return "neutral"


# --------------------------------------------------------------------------- #
# macOS `say` engine
# --------------------------------------------------------------------------- #
class SayEngine:
    name = "macos-say"

    # Only expose voices in languages the app supports (English + Indian), so
    # previews can introduce themselves natively. Other macOS languages are
    # hidden. Override with VOXFORGE_SAY_LANGS="all" or a comma list.
    SUPPORTED_LANGS = {"en", "hi", "ta", "te", "bn", "kn", "gu", "mr", "pa", "ml"}

    def __init__(self) -> None:
        self._say = shutil.which("say")
        if not self._say:
            raise EngineError("`say` not found (not macOS?)")
        self._voices: list[VoiceInfo] | None = None
        cfg = os.environ.get("VOXFORGE_SAY_LANGS", "").strip().lower()
        if cfg == "all":
            self._allowed: set[str] | None = None  # no filtering
        elif cfg:
            self._allowed = {c.strip() for c in cfg.split(",") if c.strip()}
        else:
            self._allowed = self.SUPPORTED_LANGS

    def list_voices(self) -> list[VoiceInfo]:
        # `say -v '?'` is static and slow (~2.6s) — list once and cache.
        if self._voices is not None:
            return self._voices
        out = subprocess.run(
            [self._say, "-v", "?"], capture_output=True, text=True, check=True
        ).stdout
        voices: list[VoiceInfo] = []
        for line in out.splitlines():
            # "Samantha           en_US    # Hi, my name is Samantha."
            m = re.match(r"^(.+?)\s{2,}([a-z]{2}[_-][A-Z]{2})\s+#", line)
            if not m:
                continue
            vname = m.group(1).strip()
            lang = m.group(2).replace("_", "-")
            if self._allowed is not None and lang.split("-")[0] not in self._allowed:
                continue  # hide unsupported-language macOS voices
            voices.append(
                VoiceInfo(
                    id=vname,
                    name=vname,
                    lang=lang,
                    gender=_guess_gender(vname),
                )
            )
        self._voices = voices
        return voices

    def synthesize(
        self,
        text: str,
        voice_id: str,
        rate: float,
        pitch: float,
        volume: float,
        fmt: str,
    ) -> tuple[bytes, str]:
        # Keep each voice's *natural* sound. Only deviate from defaults when the
        # user actually changes a control — forcing an absolute pitch on every
        # voice (the old behaviour) made them all sound off/robotic.
        cmd = [self._say, "-v", voice_id]

        # Rate: only override when changed (default lets the voice use its own
        # natural cadence). 1.0 -> ~175 wpm baseline.
        if abs(rate - 1.0) > 1e-3:
            cmd += ["-r", str(int(round(175 * _clamp(rate, 0.5, 2.0))))]

        # Pitch + volume via embedded commands ONLY when non-default. Embedded
        # [[pbas]] shifts a voice off its natural pitch, so skip it at 1.0.
        prefix = ""
        if abs(volume - 1.0) > 1e-3:
            prefix += f"[[volm {_clamp(volume, 0.0, 1.0):.2f}]]"
        if abs(pitch - 1.0) > 1e-3:
            # Map 0–2 around the voice's mid-range; 1.0 is natural (omitted).
            prefix += f"[[pbas {int(round(_clamp(pitch, 0.0, 2.0) * 45))}]]"

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        try:
            cmd += [
                "-o",
                wav_path,
                "--file-format=WAVE",
                "--data-format=LEI16@22050",
                prefix + text,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0 or not os.path.exists(wav_path):
                raise EngineError(proc.stderr.strip() or "say failed")
            return _finalize(wav_path, fmt)
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)


# --------------------------------------------------------------------------- #
# Piper engine (cross-platform, optional)
# --------------------------------------------------------------------------- #
class PiperEngine:
    """Neural TTS via the `piper-tts` Python package (PRD/TRD recommended).

    Uses the in-process Python API rather than the standalone binary, whose
    macOS release ships broken (missing bundled dylibs). Voice models live in
    ``models/*.onnx`` (fetched by setup.sh). Loaded models are cached.
    """

    name = "piper"

    def __init__(self) -> None:
        try:
            from piper import PiperVoice  # noqa: F401 — import probe
        except ImportError as e:
            raise EngineError("piper-tts not installed") from e

        # Only espeak-phonemised models work with this Piper build. A model
        # declaring another phoneme_type (e.g. "pinyin") synthesises to an
        # empty file, which surfaces as a request that never finishes — so
        # leave those out of the catalogue entirely.
        self._models = []
        for m in sorted(MODELS_DIR.glob("*.onnx")):
            cfg = m.with_suffix(".onnx.json")
            try:
                phoneme_type = json.loads(cfg.read_text()).get(
                    "phoneme_type", "espeak")
            except Exception:
                phoneme_type = "espeak"      # no config: let Piper decide
            if phoneme_type != "espeak":
                print(f"[voxforge] skipping {m.stem}: "
                      f"unsupported phoneme_type {phoneme_type!r}")
                continue
            self._models.append(m)
        if not self._models:
            raise EngineError("no usable .onnx voice models in models/")
        self._loaded: dict[str, object] = {}

    # Known speaker genders + quality wording for nicer picker labels.
    _KNOWN_GENDER = {
        "amy": "female",
        "lessac": "female",
        "hfc_female": "female",
        "jenny_dioco": "female",
        "kathleen": "female",
        "ryan": "male",
        "hfc_male": "male",
        "alan": "male",
        "joe": "male",
        # Indic speakers
        "priyamvada": "female",
        "maya": "female",
        "padmavathi": "female",
        "meera": "female",
        "pratham": "male",
        "rohan": "male",
        "venkatesh": "male",
        "arjun": "male",
        "fasih": "male",
    }
    _QUALITY = {"x_low": "Low", "low": "Low", "medium": "Medium", "high": "High"}
    # Indian display names for the English voices (label-only; model unchanged).
    _NAME_ALIAS = {
        "lessac": "Riya",
        "ryan": "Ishaan",
        "jenny_dioco": "Aditi",
        "amy": "Pooja",
        "hfc_female": "Naina",
    }

    def list_voices(self) -> list[VoiceInfo]:
        voices = []
        for m in self._models:
            stem = m.stem  # e.g. "en_US-lessac-high"
            parts = stem.split("-")
            locale = parts[0] if parts else "en_US"
            lang = locale.replace("_", "-")
            speaker = parts[1] if len(parts) > 1 else stem
            quality = self._QUALITY.get(parts[2], "") if len(parts) > 2 else ""
            pretty = self._NAME_ALIAS.get(speaker, speaker.replace("_", " ").title())
            label = f"{pretty} (Neural{', ' + quality if quality else ''})"
            gender = self._KNOWN_GENDER.get(speaker, _guess_gender(stem))
            voices.append(
                VoiceInfo(id=stem, name=label, lang=lang, gender=gender)
            )
        # Highest quality first so the most human-sounding voices lead.
        order = {"High": 0, "Medium": 1, "Low": 2, "": 3}
        voices.sort(key=lambda v: order.get(v.name.split(", ")[-1].rstrip(")"), 3))
        return voices

    def _voice(self, voice_id: str):
        if voice_id in self._loaded:
            return self._loaded[voice_id]
        for m in self._models:
            if m.stem == voice_id:
                from piper import PiperVoice

                v = PiperVoice.load(str(m))
                self._loaded[voice_id] = v
                return v
        raise EngineError(f"unknown voice {voice_id}")

    def synthesize(
        self,
        text: str,
        voice_id: str,
        rate: float,
        pitch: float,  # noqa: ARG002 — Piper has no live pitch control
        volume: float,
        fmt: str,
    ) -> tuple[bytes, str]:
        import wave

        from piper import SynthesisConfig

        voice = self._voice(voice_id)
        # length_scale is inverse of speed: faster speech = smaller scale.
        # normalize_audio=False so _polish_wav owns headroom (Piper's own
        # normalize pushes the peak to full scale and clips).
        cfg = SynthesisConfig(
            length_scale=_pace(voice_id) / _clamp(rate, 0.5, 2.0),
            volume=_clamp(volume, 0.0, 1.0),
            normalize_audio=False,
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        try:
            with wave.open(wav_path, "wb") as wf:
                voice.synthesize_wav(text, wf, syn_config=cfg)  # type: ignore[attr-defined]
            return _finalize(wav_path, fmt, pitch=pitch, volume=volume)
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)


# Some Piper models speak noticeably slower than a native speaker would, which
# reads as hesitant rather than calm. The correction is a baseline length_scale
# per voice, so a user-supplied rate still scales from the voice's *natural*
# pace rather than from the model's sluggish default.
#
# Measured on hi_IN with Whisper: word-error rate is unchanged from 1.00 down
# to 0.84 (every difference sat inside the +/-10pt run-to-run spread), so 0.88
# is well inside the safe range. Raising noise_w_scale was tried for the same
# "robotic" complaint and made intelligibility *worse* - do not re-add it.
_VOICE_PACE = {
    "hi_in-priyamvada-medium": 0.88,   # 2.4-2.8 w/s -> ~3.0, matching svara
    "hi_in-rohan-medium": 0.88,        # 2.3 w/s, the slowest we serve
}


def _pace(voice_id: str) -> float:
    """Baseline length_scale for a voice; 1.0 leaves the model untouched."""
    v = (voice_id or "").lower().replace("server:", "")
    return _VOICE_PACE.get(v, 1.0)


# --------------------------------------------------------------------------- #
# Kokoro engine (most natural, optional) — best quality/size open TTS
# --------------------------------------------------------------------------- #
class KokoroEngine:
    """Kokoro-82M neural TTS via `kokoro-onnx` (Apache-2.0, runs on CPU).

    The most human-sounding self-hosted engine available — richer prosody and
    timbre than Piper. Model files live in ``models/kokoro/``:
    ``kokoro-v1.0.onnx`` + ``voices-v1.0.bin`` (fetched by setup.sh).
    """

    name = "kokoro"
    SR = 24000

    # Curated, best-sounding subset. Each entry:
    #   id -> (display name, BCP-47 lang tag, gender, kokoro g2p lang code)
    # Kokoro voice ids encode region (a=US, b=GB, h=Hindi) + gender (f/m).
    # Indian display names (voice ids/engine unchanged — labels only).
    _CURATED = {
        # English (US) voices
        "af_heart": ("Prapti", "en-US", "female", "en-us"),
        "af_bella": ("Seema", "en-US", "female", "en-us"),
        "af_nicole": ("Sanghamitra", "en-US", "female", "en-us"),
        "af_aoede": ("Ananya", "en-US", "female", "en-us"),
        "am_michael": ("Ayaan", "en-US", "male", "en-us"),
        "am_fenrir": ("Ronith", "en-US", "male", "en-us"),
        "am_puck": ("Rounak", "en-US", "male", "en-us"),
        # English (UK) voices
        "bf_emma": ("Priya", "en-GB", "female", "en-gb"),
        "bf_isabella": ("Isha", "en-GB", "female", "en-gb"),
        "bm_george": ("Aditya", "en-GB", "male", "en-gb"),
        "bm_fable": ("Vihaan", "en-GB", "male", "en-gb"),
        # Hindi / India
        "hf_alpha": ("Aria · Hindi", "hi-IN", "female", "hi"),
        "hf_beta": ("Diya · Hindi", "hi-IN", "female", "hi"),
        "hm_omega": ("Arjun · Hindi", "hi-IN", "male", "hi"),
        "hm_psi": ("Kabir · Hindi", "hi-IN", "male", "hi"),
        # Mandarin Chinese (espeak g2p code "cmn")
        "zf_xiaoxiao": ("Xiaoxiao · Chinese", "zh-CN", "female", "cmn"),
        "zf_xiaoyi": ("Xiaoyi · Chinese", "zh-CN", "female", "cmn"),
        "zf_xiaobei": ("Xiaobei · Chinese", "zh-CN", "female", "cmn"),
        "zf_xiaoni": ("Xiaoni · Chinese", "zh-CN", "female", "cmn"),
        "zm_yunyang": ("Yunyang · Chinese", "zh-CN", "male", "cmn"),
        "zm_yunxi": ("Yunxi · Chinese", "zh-CN", "male", "cmn"),
        "zm_yunjian": ("Yunjian · Chinese", "zh-CN", "male", "cmn"),
        "zm_yunxia": ("Yunxia · Chinese", "zh-CN", "male", "cmn"),
    }

    def __init__(self) -> None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError as e:
            raise EngineError("kokoro-onnx not installed") from e
        base = MODELS_DIR / "kokoro"
        model = base / "kokoro-v1.0.onnx"
        voices = base / "voices-v1.0.bin"
        if not (model.exists() and voices.exists()):
            raise EngineError("kokoro model files missing in models/kokoro/")
        self._k = Kokoro(str(model), str(voices))
        avail = set(self._k.get_voices())
        # Keep curated voices that actually exist in this voices file.
        self._voices = {vid: meta for vid, meta in self._CURATED.items() if vid in avail}
        if not self._voices:
            # Fall back to whatever the file ships if our curation misses.
            self._voices = {
                v: (v, "en-US", _guess_gender(v), "en-us") for v in sorted(avail)
            }

    def list_voices(self) -> list[VoiceInfo]:
        out = []
        for vid, (pretty, lang, gender, _glang) in self._voices.items():
            out.append(
                VoiceInfo(
                    id=vid,
                    name=f"{pretty} (Kokoro, Ultra)",
                    lang=lang,
                    gender=gender,
                )
            )
        return out

    def synthesize(
        self,
        text: str,
        voice_id: str,
        rate: float,
        pitch: float,  # noqa: ARG002 — no native pitch control
        volume: float,  # noqa: ARG002 — applied by _polish_wav / client
        fmt: str,
    ) -> tuple[bytes, str]:
        import wave

        import numpy as np

        if voice_id not in self._voices:
            raise EngineError(f"unknown voice {voice_id}")
        glang = self._voices[voice_id][3]  # kokoro g2p code, e.g. "hi", "en-us"
        samples, sr = self._k.create(
            text, voice=voice_id, speed=_clamp(rate, 0.5, 2.0), lang=glang
        )
        pcm = np.clip(np.asarray(samples) * 32768.0, -32768, 32767).astype(np.int16)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(pcm.tobytes())
            return _finalize(wav_path, fmt, pitch=pitch, volume=volume)
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)


# --------------------------------------------------------------------------- #
# MMS engine (Meta Massively Multilingual Speech) — broad Indian-language cover
# --------------------------------------------------------------------------- #
class MMSEngine:
    """Neural TTS for languages no other engine covers, via Meta's MMS-TTS
    (VITS) models through `transformers` + `torch`. 16 kHz, CC-BY-NC 4.0.

    Used here for Indian languages absent from Kokoro/Piper: Tamil, Bengali,
    Kannada, Gujarati, Marathi, Punjabi. Models are cached under
    ``models/mms/`` and loaded lazily on first use.
    """

    name = "mms"
    MMS_DIR = MODELS_DIR / "mms"

    # id -> (display, BCP-47, gender, hf model id)
    _LANGS = {
        "mms-tam": ("Tamil", "ta-IN", "neutral", "facebook/mms-tts-tam"),
        "mms-tel": ("Telugu", "te-IN", "neutral", "facebook/mms-tts-tel"),
        "mms-mal": ("Malayalam", "ml-IN", "neutral", "facebook/mms-tts-mal"),
        "mms-hin": ("Hindi", "hi-IN", "neutral", "facebook/mms-tts-hin"),
        "mms-ory": ("Odia", "or-IN", "neutral", "facebook/mms-tts-ory"),
        "mms-asm": ("Assamese", "as-IN", "neutral", "facebook/mms-tts-asm"),
        "mms-mai": ("Maithili", "mai-IN", "neutral", "facebook/mms-tts-mai"),
        "mms-ben": ("Bengali", "bn-IN", "neutral", "facebook/mms-tts-ben"),
        "mms-kan": ("Kannada", "kn-IN", "neutral", "facebook/mms-tts-kan"),
        "mms-guj": ("Gujarati", "gu-IN", "neutral", "facebook/mms-tts-guj"),
        "mms-mar": ("Marathi", "mr-IN", "neutral", "facebook/mms-tts-mar"),
        "mms-pan": ("Punjabi", "pa-IN", "neutral", "facebook/mms-tts-pan"),
    }

    def __init__(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import VitsModel  # noqa: F401
        except ImportError as e:
            raise EngineError("torch/transformers not installed") from e

        # Only advertise languages whose model is already in the local cache,
        # so the picker never shows a voice that would fail on first synth.
        self._available = {
            vid: meta
            for vid, meta in self._LANGS.items()
            if self._cached(meta[3])
        }
        if not self._available:
            raise EngineError("no MMS models downloaded (run setup.sh)")
        self._loaded: dict[str, tuple] = {}

    def _cached(self, model_id: str) -> bool:
        # transformers stores snapshots as models--facebook--mms-tts-xxx/
        folder = "models--" + model_id.replace("/", "--")
        return (self.MMS_DIR / folder).exists()

    def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(
                id=vid,
                name=f"{disp} (Neural, MMS)",
                lang=lang,
                gender=gender,
            )
            for vid, (disp, lang, gender, _m) in self._available.items()
        ]

    def _load(self, vid: str):
        if vid in self._loaded:
            return self._loaded[vid]
        import torch
        from transformers import AutoTokenizer, VitsModel

        model_id = self._available[vid][3]
        model = VitsModel.from_pretrained(model_id, cache_dir=str(self.MMS_DIR))
        tok = AutoTokenizer.from_pretrained(model_id, cache_dir=str(self.MMS_DIR))
        model = model.to(torch_device()).eval()
        _configure_torch()
        self._loaded[vid] = (model, tok)
        return self._loaded[vid]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        rate: float,
        pitch: float,  # noqa: ARG002 — VITS has no live pitch control
        volume: float,  # noqa: ARG002 — applied by _polish_wav
        fmt: str,
    ) -> tuple[bytes, str]:
        import wave

        import numpy as np
        import torch

        if voice_id not in self._available:
            raise EngineError(f"unknown voice {voice_id}")
        # Serialize torch work so concurrent/warm-up inference can't race.
        with _TORCH_LOCK:
            model, tok = self._load(voice_id)
            # VITS: higher speaking_rate = faster speech.
            model.speaking_rate = _clamp(rate, 0.5, 2.0)
            inputs = tok(text, return_tensors="pt").to(torch_device())
            # This tokenizer silently drops characters outside its own script,
            # so text in another alphabet leaves nothing to speak.
            ids = inputs.get("input_ids")
            if ids is None or ids.numel() == 0:
                lang = self._available[voice_id][0]
                raise EngineError(
                    f"This voice speaks {lang}. Please enter {lang} text, "
                    f"or choose a voice for the language you typed."
                )
            with torch.inference_mode():
                wave_t = model(**inputs).waveform  # (1, n) float32
            samples = wave_t.squeeze().cpu().numpy().astype(np.float32)
            sr = int(model.config.sampling_rate)
        pcm = np.clip(samples * 32768.0, -32768, 32767).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(pcm.tobytes())
            return _finalize(wav_path, fmt, pitch=pitch, volume=volume)
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)


# --------------------------------------------------------------------------- #
# Parler engine (AI4Bharat Indic Parler-TTS) — most human Indian voices, "HD"
# --------------------------------------------------------------------------- #
class ParlerEngine:
    """AI4Bharat Indic Parler-TTS — the most natural open Indian voices, close
    to a real human. Heavy (~2.3 GB, CPU-only here) so generation is slow; it's
    offered as an opt-in "HD" tier alongside the fast engines.

    Model cached under ``models/parler/``. Loaded lazily on first use.
    """

    name = "parler-hd"
    PARLER_DIR = MODELS_DIR / "parler"
    MODEL_ID = "ai4bharat/indic-parler-tts"

    # This engine understands the optional `emotion` argument (see synthesize).
    supports_emotion = True

    # Emotion presets — Parler is description-driven, so we steer delivery by
    # phrasing the speaker description. Keys are the public emotion ids.
    _EMOTIONS = {
        "neutral": "in a warm, expressive and natural tone",
        "happy": "in a cheerful, upbeat and happy tone with bright, lively energy",
        "excited": "in a very excited, enthusiastic and energetic tone, "
        "speaking with high expressiveness",
        "calm": "in a calm, soft, soothing and relaxed tone",
        "sad": "in a soft, sad and melancholic tone, gently and slowly",
        "serious": "in a serious, firm and confident, authoritative tone",
        "angry": "in an intense, forceful and angry tone",
    }

    # Full Indic Parler-TTS speaker set: lang_code -> (lang_name, bcp47, [(speaker, gender)])
    _SPEAKERS = {
        "as": ("Assamese", "as-IN", [("Amit", "male"), ("Sita", "female"), ("Poonam", "female"), ("Rakesh", "male")]),
        "bn": ("Bengali", "bn-IN", [("Arjun", "male"), ("Aditi", "female"), ("Tapan", "male"), ("Rashmi", "female"), ("Arnav", "male"), ("Riya", "female")]),
        "brx": ("Bodo", "brx-IN", [("Bikram", "male"), ("Maya", "female"), ("Kalpana", "female")]),
        "hne": ("Chhattisgarhi", "hne-IN", [("Bhanu", "male"), ("Champa", "female")]),
        "doi": ("Dogri", "doi-IN", [("Karan", "male")]),
        "en": ("English (Indian)", "en-IN", [("Thoma", "male"), ("Mary", "female"), ("Swapna", "female"), ("Dinesh", "male"), ("Meera", "female"), ("Jatin", "male"), ("Aakash", "male"), ("Sneha", "female"), ("Kabir", "male"), ("Tisha", "female"), ("Chingkhei", "male"), ("Thoiba", "male"), ("Priya", "female"), ("Tarun", "male"), ("Gauri", "female"), ("Nisha", "female"), ("Raghav", "male"), ("Kavya", "female"), ("Ravi", "male"), ("Vikas", "male"), ("Riya", "female")]),
        "gu": ("Gujarati", "gu-IN", [("Yash", "male"), ("Neha", "female")]),
        "hi": ("Hindi", "hi-IN", [("Rohit", "male"), ("Divya", "female"), ("Aman", "male"), ("Rani", "female")]),
        "kn": ("Kannada", "kn-IN", [("Suresh", "male"), ("Anu", "female"), ("Chetan", "male"), ("Vidya", "female")]),
        "ml": ("Malayalam", "ml-IN", [("Anjali", "female"), ("Anju", "female"), ("Harish", "male")]),
        "mni": ("Manipuri", "mni-IN", [("Laishram", "male"), ("Ranjit", "male")]),
        "mr": ("Marathi", "mr-IN", [("Sanjay", "male"), ("Sunita", "female"), ("Nikhil", "male"), ("Radha", "female"), ("Varun", "male"), ("Isha", "female")]),
        "ne": ("Nepali", "ne-NP", [("Amrita", "female")]),
        "or": ("Odia", "or-IN", [("Manas", "male"), ("Debjani", "female")]),
        "pa": ("Punjabi", "pa-IN", [("Divjot", "male"), ("Gurpreet", "male")]),
        "sa": ("Sanskrit", "sa-IN", [("Aryan", "male")]),
        "ta": ("Tamil", "ta-IN", [("Kavitha", "female"), ("Jaya", "female")]),
        "te": ("Telugu", "te-IN", [("Prakash", "male"), ("Lalitha", "female"), ("Kiran", "male")]),
    }
    # id -> (display, BCP-47, gender, speaker[, style]) — all 69 official speakers.
    _VOICES = {
        f"parler-{code}-{spk.lower()}": (f"{spk} · {lname}", bcp, g, spk)
        for code, (lname, bcp, spks) in _SPEAKERS.items()
        for spk, g in spks
    }
    # Extra distinct Hindi voices (a base speaker + a tailored vocal-style prompt).
    _VOICES.update({
        "parler-hi-vikram": ("Vikram · Hindi (deep)", "hi-IN", "male", "Rohit",
                             "in a deep, mature, resonant low-pitched masculine voice"),
        "parler-hi-arjun": ("Arjun · Hindi (young)", "hi-IN", "male", "Aman",
                            "in a youthful, bright, energetic higher-pitched voice"),
        "parler-hi-raghav2": ("Raghav · Hindi (calm)", "hi-IN", "male", "Rohit",
                              "in a calm, soft, gentle and soothing voice"),
        "parler-hi-dev": ("Dev · Hindi (warm)", "hi-IN", "male", "Aman",
                          "in a warm, friendly, slightly husky voice"),
        "parler-hi-manoj": ("Manoj · Hindi (anchor)", "hi-IN", "male", "Rohit",
                            "in a confident, clear, authoritative news-anchor style voice"),
        "parler-hi-priya2": ("Priya · Hindi (soft)", "hi-IN", "female", "Divya",
                             "in a soft, gentle, warm and tender feminine voice"),
        "parler-hi-anjali2": ("Anjali · Hindi (bright)", "hi-IN", "female", "Rani",
                              "in a bright, cheerful, youthful higher-pitched voice"),
        "parler-hi-meera2": ("Meera · Hindi (mature)", "hi-IN", "female", "Divya",
                             "in a mature, calm, elegant and graceful voice"),
        "parler-hi-sneha2": ("Sneha · Hindi (sweet)", "hi-IN", "female", "Rani",
                             "in a sweet, expressive, melodious voice"),
        "parler-hi-kavita": ("Kavita · Hindi (storyteller)", "hi-IN", "female", "Divya",
                             "in a soft, expressive, warm storytelling voice"),
        # Bhojpuri — uses Hindi base speakers (shared Devanagari + phonology) so
        # Bhojpuri text is read naturally; no native Bhojpuri TTS exists open-source.
        "parler-bho-manish": ("Manish · Bhojpuri", "bho-IN", "male", "Rohit"),
        "parler-bho-vijay": ("Vijay · Bhojpuri", "bho-IN", "male", "Aman"),
        "parler-bho-sushma": ("Sushma · Bhojpuri", "bho-IN", "female", "Divya"),
        "parler-bho-gita": ("Gita · Bhojpuri", "bho-IN", "female", "Rani"),
        "parler-bho-ramesh": ("Ramesh · Bhojpuri (deep)", "bho-IN", "male", "Rohit",
                              "in a deep, mature, resonant masculine voice"),
        "parler-bho-radha": ("Radha · Bhojpuri (soft)", "bho-IN", "female", "Rani",
                             "in a soft, gentle, warm feminine voice"),
        # Top-ups for languages with few base speakers (style variants).
        "parler-ta-anitha": ("Anitha · Tamil (soft)", "ta-IN", "female", "Kavitha",
                             "in a soft, gentle, warm feminine voice"),
        "parler-ta-deepa": ("Deepa · Tamil (bright)", "ta-IN", "female", "Jaya",
                            "in a bright, cheerful, youthful voice"),
        "parler-gu-meena": ("Meena · Gujarati (soft)", "gu-IN", "female", "Neha",
                            "in a soft, gentle, warm feminine voice"),
        "parler-gu-raj": ("Raj · Gujarati (deep)", "gu-IN", "male", "Yash",
                          "in a deep, mature, resonant masculine voice"),
        "parler-pa-jass": ("Jass · Punjabi (deep)", "pa-IN", "male", "Gurpreet",
                           "in a deep, mature, resonant masculine voice"),
        "parler-pa-sukh": ("Sukh · Punjabi (young)", "pa-IN", "male", "Divjot",
                           "in a youthful, bright, energetic voice"),
        "parler-or-priya": ("Priya · Odia (soft)", "or-IN", "female", "Debjani",
                            "in a soft, gentle, warm feminine voice"),
        "parler-or-bibhu": ("Bibhu · Odia (deep)", "or-IN", "male", "Manas",
                            "in a deep, mature, resonant masculine voice"),
    })

    def __init__(self) -> None:
        try:
            from parler_tts import ParlerTTSForConditionalGeneration  # noqa: F401
        except ImportError as e:
            raise EngineError("parler-tts not installed") from e
        # Only advertise voices once the model is cached locally.
        folder = "models--" + self.MODEL_ID.replace("/", "--")
        if not (self.PARLER_DIR / folder).exists():
            raise EngineError("parler model not downloaded (run setup.sh parler)")
        self._model = None
        self._tok = None
        self._desc_tok = None
        self._device = "cpu"

    def list_voices(self) -> list[VoiceInfo]:
        # entries are (display, lang, gender, speaker[, style]) — style optional
        return [
            VoiceInfo(id=vid, name=f"{v[0]} (Parler, HD)", lang=v[1], gender=v[2])
            for vid, v in self._VOICES.items()
        ]

    def _load(self):
        if self._model is not None:
            return
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        cache = str(self.PARLER_DIR)
        self._device = torch_device()
        # fp16 on CUDA for speed; full precision on CPU/MPS for stability.
        dtype = torch.float16 if self._device == "cuda" else torch.float32
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            self.MODEL_ID, cache_dir=cache, torch_dtype=dtype
        )
        if self._device == "cpu":
            # INT8 quant only helps some CPUs (guarded; no-op on failure).
            model = _maybe_quantize(model)
        self._model = model.to(self._device).eval()
        self._tok = AutoTokenizer.from_pretrained(self.MODEL_ID, cache_dir=cache)
        # Description encoder may use a different tokenizer.
        desc_name = getattr(self._model.config, "text_encoder", None)
        desc_id = getattr(desc_name, "_name_or_path", self.MODEL_ID)
        self._desc_tok = AutoTokenizer.from_pretrained(desc_id, cache_dir=cache)
        _configure_torch()
        print(f"[voxforge] Parler loaded on {self._device} ({dtype})")

    def synthesize(
        self,
        text: str,
        voice_id: str,
        rate: float,  # noqa: ARG002 — pacing controlled via the description
        pitch: float,  # noqa: ARG002
        volume: float,  # noqa: ARG002 — applied by _polish_wav
        fmt: str,
        emotion: str = "neutral",
    ) -> tuple[bytes, str]:
        import wave

        import numpy as np
        import torch

        if voice_id not in self._VOICES:
            raise EngineError(f"unknown voice {voice_id}")
        entry = self._VOICES[voice_id]
        speaker = entry[3]
        style = entry[4] if len(entry) > 4 else ""
        pace = "slightly slowly" if rate < 0.95 else "at a moderate pace"
        tone = emotion_mod.feel(emotion).parler
        style_clause = f", {style}" if style else ""
        description = (
            f"{speaker} speaks {pace} {tone}{style_clause}, "
            "sounding like a real person, with very clear, high-quality, "
            "close-microphone audio and no background noise."
        )

        use_bf16 = os.environ.get("VOXFORGE_BF16", "0") == "1"
        # Serialize torch work (model load + generate) so a background warm-up
        # or another request can never run torch inference concurrently.
        with _TORCH_LOCK:
            self._load()
            dev = self._device
            desc = self._desc_tok(description, return_tensors="pt").to(dev)
            prompt = self._tok(text, return_tensors="pt").to(dev)
            kwargs = dict(
                input_ids=desc.input_ids,
                attention_mask=desc.attention_mask,
                prompt_input_ids=prompt.input_ids,
                prompt_attention_mask=prompt.attention_mask,
            )
            with torch.inference_mode():
                if use_bf16:
                    try:
                        with torch.autocast("cpu", dtype=torch.bfloat16):
                            gen = self._model.generate(**kwargs)
                    except Exception:
                        gen = self._model.generate(**kwargs)  # fp32 fallback
                else:
                    gen = self._model.generate(**kwargs)
            samples = gen.cpu().numpy().squeeze().astype(np.float32)
            sr = int(self._model.config.sampling_rate)
        pcm = np.clip(samples * 32768.0, -32768, 32767).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(pcm.tobytes())
            # Parler reads fast by default — nudge ~10% slower for a comfortable
            # default pace (QA #5, Divya/Hindi too fast).
            return _finalize(
                wav_path, fmt, speed=rate * 0.9, pitch=pitch, volume=volume
            )
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)


class ChatterboxEngine:
    """Premium expressive English voices via the isolated Chatterbox service
    (Resemble AI, MIT). The model runs in a separate venv/process (see
    chatterbox_service.py) to keep its newer torch away from the main stack;
    here we just call it over localhost HTTP and finalize the audio."""

    name = "chatterbox"
    supports_emotion = True
    URL = os.environ.get("VOXFORGE_CHATTERBOX_URL", "http://127.0.0.1:8001")

    # id -> (display, BCP-47, gender, Chatterbox language_id).
    # The multilingual model speaks all of these with a built-in expressive
    # speaker; emotion is steered per request.
    _VOICES = {
        "chatterbox-en-aria": ("Aria · English", "en-US", "female", "en"),
        "chatterbox-hi-ananya": ("Ananya · Hindi", "hi-IN", "female", "hi"),
        "chatterbox-es-sofia": ("Sofia · Spanish", "es-ES", "female", "es"),
        "chatterbox-fr-camille": ("Camille · French", "fr-FR", "female", "fr"),
        "chatterbox-de-lena": ("Lena · German", "de-DE", "female", "de"),
        "chatterbox-it-giulia": ("Giulia · Italian", "it-IT", "female", "it"),
        "chatterbox-pt-beatriz": ("Beatriz · Portuguese", "pt-PT", "female", "pt"),
        "chatterbox-ru-anya": ("Anya · Russian", "ru-RU", "female", "ru"),
        "chatterbox-zh-mei": ("Mei · Chinese", "zh-CN", "female", "zh"),
        "chatterbox-ja-sakura": ("Sakura · Japanese", "ja-JP", "female", "ja"),
        "chatterbox-ko-jiwoo": ("Jiwoo · Korean", "ko-KR", "female", "ko"),
        "chatterbox-ar-layla": ("Layla · Arabic", "ar", "female", "ar"),
        "chatterbox-tr-elif": ("Elif · Turkish", "tr-TR", "female", "tr"),
        "chatterbox-pl-zofia": ("Zofia · Polish", "pl-PL", "female", "pl"),
        "chatterbox-nl-sanne": ("Sanne · Dutch", "nl-NL", "female", "nl"),
        "chatterbox-sv-elsa": ("Elsa · Swedish", "sv-SE", "female", "sv"),
        "chatterbox-da-freja": ("Freja · Danish", "da-DK", "female", "da"),
        "chatterbox-no-ingrid": ("Ingrid · Norwegian", "nb-NO", "female", "no"),
        "chatterbox-fi-aino": ("Aino · Finnish", "fi-FI", "female", "fi"),
        "chatterbox-el-eleni": ("Eleni · Greek", "el-GR", "female", "el"),
        "chatterbox-he-noa": ("Noa · Hebrew", "he-IL", "female", "he"),
        "chatterbox-ms-nadia": ("Nadia · Malay", "ms-MY", "female", "ms"),
        "chatterbox-sw-zuri": ("Zuri · Swahili", "sw-KE", "female", "sw"),
    }

    def __init__(self) -> None:
        # Advertise only if the local service is reachable (TCP connect).
        import socket
        from urllib.parse import urlparse

        u = urlparse(self.URL)
        try:
            with socket.create_connection((u.hostname, u.port or 80), timeout=2):
                pass
        except OSError as e:
            raise EngineError("chatterbox service not running") from e

    def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(
                id=vid, name=f"{disp} (Chatterbox, Expressive)", lang=lang, gender=g
            )
            for vid, (disp, lang, g, _lc) in self._VOICES.items()
        ]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        rate: float,  # noqa: ARG002 — pacing controlled by the emotion preset
        pitch: float,  # noqa: ARG002
        volume: float,  # noqa: ARG002 — applied by _polish_wav
        fmt: str,
        emotion: str = "neutral",
    ) -> tuple[bytes, str]:
        if voice_id not in self._VOICES:
            raise EngineError(f"unknown voice {voice_id}")
        language_id = self._VOICES[voice_id][3]
        return chatterbox_synth(
            text,
            language_id=language_id,
            emotion=emotion,
            fmt=fmt,
            speed=rate,
            pitch=pitch,
            volume=volume,
        )


def chatterbox_synth(
    text: str,
    *,
    language_id: str = "en",
    emotion: str = "neutral",
    exaggeration: tuple[float, float] | None = None,
    fmt: str = "wav",
    audio_prompt_path: str | None = None,
    url: str | None = None,
    speed: float = 1.0,
    pitch: float = 1.0,
    volume: float = 1.0,
) -> tuple[bytes, str]:
    """Call the isolated Chatterbox service and finalize the audio. Shared by the
    built-in expressive voices and by cloned (user-uploaded) voices."""
    import urllib.request

    url = url or ChatterboxEngine.URL
    body: dict = {"text": text, "emotion": emotion, "language_id": language_id}
    ex, cfg = exaggeration or emotion_mod.feel(emotion).cbx
    body["exaggeration"], body["cfg_weight"] = ex, cfg
    if audio_prompt_path:
        body["audio_prompt_path"] = audio_prompt_path
    req = urllib.request.Request(
        url + "/tts",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            audio = r.read()
    except Exception as e:
        raise EngineError(f"chatterbox synthesis failed: {e}") from e

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name
        tf.write(audio)
    try:
        return _finalize(wav_path, fmt, speed=speed, pitch=pitch, volume=volume)
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def if5_synth(
    text: str,
    ref_audio_path: str,
    ref_text: str,
    *,
    fmt: str = "wav",
    speed: float = 1.0,
    pitch: float = 1.0,
    volume: float = 1.0,
    url: str | None = None,
) -> tuple[bytes, str]:
    """Call the IndicF5 microservice (:8004) — near-human Indic TTS + cloning.
    Speaks `text` in the voice of the reference clip + its transcript."""
    import urllib.request

    url = url or os.environ.get("IF5_URL", "http://127.0.0.1:8004")
    body = {"text": text, "ref_audio_path": ref_audio_path, "ref_text": ref_text}
    req = urllib.request.Request(
        url + "/tts", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            audio = r.read()
    except Exception as e:
        raise EngineError(f"IndicF5 synthesis failed: {e}") from e
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name
        tf.write(audio)
    try:
        return _finalize(wav_path, fmt, speed=speed, pitch=pitch, volume=volume)
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def vagdhenu_synth(
    text: str,
    *,
    meter: str = "auto",  # sidecar detects the verse metre
    seed: int = 0,
    fmt: str = "wav",
    speed: float = 1.0,
    pitch: float = 1.0,
    volume: float = 1.0,
    url: str | None = None,
) -> tuple[bytes, str]:
    """Call the Vāgdhenu microservice (:8006) — Sanskrit chant / pārāyaṇa TTS.
    Chants metered Sanskrit verse (Devanagari) with a melodic contour."""
    import urllib.request

    url = url or os.environ.get("VAGDHENU_URL", "http://127.0.0.1:8006")
    body = {"text": text, "meter": meter, "seed": seed}
    req = urllib.request.Request(
        url + "/chant", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            audio = r.read()
    except Exception as e:
        raise EngineError(f"Vagdhenu synthesis failed: {e}") from e
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name
        tf.write(audio)
    try:
        return _finalize(wav_path, fmt, speed=speed, pitch=pitch, volume=volume)
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


# --------------------------------------------------------------------------- #
# Composite — expose every available engine's voices at once
# --------------------------------------------------------------------------- #
class SvaraEngine:
    """Real emotional Indic speech via svara-TTS (kenpath/svara-tts-v1, Apache-2.0).

    Runs on a separate GPU host (3B model, needs 16GB+ VRAM) exposing an
    OpenAI-compatible /v1/audio/speech endpoint. Emotion is a sentence-END tag
    (<happy> <sad> <anger> <fear> <surprise>) — genuinely learned expression, not
    the DSP pitch shift the CPU engines fall back on.

    Set VOXFORGE_SVARA_URL to the GPU host. When that host is stopped the probe
    below fails and this engine is skipped, so the catalog quietly loses these
    voices instead of erroring.
    """

    name = "svara"
    supports_emotion = True
    # below this, output quality collapses (measured) — pad instead
    _MIN_CHARS = 25
    URL = os.environ.get("VOXFORGE_SVARA_URL", "")

    # id -> (display, BCP-47, gender, svara voice_id)
    _VOICES = {
        "svara-te-f": ("Telugu", "te-IN", "female", "te_female"),
        "svara-te-m": ("Telugu", "te-IN", "male", "te_male"),
        "svara-hi-f": ("Hindi", "hi-IN", "female", "ananya"),
        "svara-hi-m": ("Hindi", "hi-IN", "male", "aditya"),
        "svara-hi-f2": ("Hindi (alt)", "hi-IN", "female", "hi_female"),
        "svara-hi-m2": ("Hindi (alt)", "hi-IN", "male", "hi_male"),
        "svara-sa-m": ("Sanskrit", "sa-IN", "male", "sa_male"),
        "svara-sa-f": ("Sanskrit", "sa-IN", "female", "sa_female"),
        "svara-ta-f": ("Tamil", "ta-IN", "female", "ta_female"),
        "svara-ta-m": ("Tamil", "ta-IN", "male", "ta_male"),
        "svara-kn-f": ("Kannada", "kn-IN", "female", "kn_female"),
        "svara-kn-m": ("Kannada", "kn-IN", "male", "kn_male"),
        "svara-ml-f": ("Malayalam", "ml-IN", "female", "ml_female"),
        "svara-ml-m": ("Malayalam", "ml-IN", "male", "ml_male"),
        "svara-bn-f": ("Bengali", "bn-IN", "female", "bn_female"),
        "svara-bn-m": ("Bengali", "bn-IN", "male", "bn_male"),
        "svara-mr-f": ("Marathi", "mr-IN", "female", "mr_female"),
        "svara-mr-m": ("Marathi", "mr-IN", "male", "mr_male"),
        "svara-gu-f": ("Gujarati", "gu-IN", "female", "gu_female"),
        "svara-gu-m": ("Gujarati", "gu-IN", "male", "gu_male"),
        "svara-pa-f": ("Punjabi", "pa-IN", "female", "pa_female"),
        "svara-pa-m": ("Punjabi", "pa-IN", "male", "pa_male"),
        "svara-as-f": ("Assamese", "as-IN", "female", "as_female"),
        "svara-or-f": ("Odia", "or-IN", "female", "or_female"),
        "svara-ne-f": ("Nepali", "ne-NP", "female", "ne_female"),
        "svara-en-f": ("English (Indian)", "en-IN", "female", "en_female"),
        "svara-en-m": ("English (Indian)", "en-IN", "male", "en_male"),
    }

    # our emotion vocabulary -> svara sentence-end tag ("" = no tag / neutral)
    _EMO_TAG = {
        "happy": "<happy>", "excited": "<happy>",
        "sad": "<sad>", "calm": "<sad>",
        "angry": "<anger>", "anger": "<anger>",
        "serious": "", "neutral": "",
    }

    def __init__(self) -> None:
        if not self.URL:
            raise EngineError("svara: VOXFORGE_SVARA_URL not set")
        import json as _json
        import urllib.request
        try:
            with urllib.request.urlopen(self.URL.rstrip("/") + "/health", timeout=4) as r:
                if _json.loads(r.read()).get("status") != "healthy":
                    raise EngineError("svara service not healthy")
        except EngineError:
            raise
        except Exception as e:
            raise EngineError(f"svara service unreachable: {e}") from e

    def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id=vid, name=f"{disp} (Svara, Emotional)", lang=lang, gender=g)
            for vid, (disp, lang, g, _sv) in self._VOICES.items()
        ]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        rate: float,
        pitch: float,  # noqa: ARG002 — expression comes from the model, not DSP
        volume: float,  # noqa: ARG002 — applied by the shared finalizer
        fmt: str,
        emotion: str = "neutral",
    ) -> tuple[bytes, str]:
        if voice_id not in self._VOICES:
            raise EngineError(f"unknown voice {voice_id}")
        import json as _json
        import urllib.request

        svara_voice = self._VOICES[voice_id][3]
        lang = self._VOICES[voice_id][1]
        tag = emotion_mod.feel((emotion or "neutral").lower()).svara

        # Very short inputs make this model mumble — measured 56% speech and a
        # 13% level (vs ~78%/84% on a full sentence), which loudness matching
        # cannot rescue because there is barely any signal. Pad to a floor with
        # a trailing pause so the model has enough context to settle.
        body = text.strip()
        if len(body) < self._MIN_CHARS:
            body = body + " " + ("\u0964" if lang.endswith("-IN") else ".")

        # Low temperature lengthened dead gaps in Hindi (0.80s at t=0.4 vs
        # 0.34s at t=0.6), so keep Indic sampling in the tighter band.
        # MEASURED on Hindi (2 takes per setting, same sentence): 0.8/0.95/1.05
        # widens the melody 7.1 -> 8.8 semitones and shortens the worst internal
        # gap 0.39s -> 0.32s versus 0.7/0.9/1.1 — i.e. less flat, less choppy.
        hindi = lang == "hi-IN"
        temp = 0.8 if hindi else 0.6

        payload = {
            "model": "svara-tts-v1",
            "voice": svara_voice,
            "input": f"{body} {tag}".strip(),
            "response_format": "wav",
            "temperature": temp,
            "top_p": 0.95 if hindi else 0.9,
            "repetition_penalty": 1.05 if hindi else 1.1,
            # svara ignores `speed` (measured: 0.80 and 1.00 give the same
            # duration over 4 takes), so tempo is applied in _finalize below.
            "speed": 1.0,
        }
        req = urllib.request.Request(
            self.URL.rstrip("/") + "/v1/audio/speech",
            data=_json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                wav = r.read()
        except Exception as e:
            raise EngineError(f"svara synthesis failed: {e}") from e
        # Shared finalizer: loudness-match + peak-safety, so svara output sits at
        # the same level as every other engine (raw svara Telugu is ~13dB quiet).
        # It works on a file, and pitch stays 1.0 — expression is the model's job.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(wav)
            wav_path = tf.name
        try:
            return _finalize(wav_path, fmt, speed=float(rate or 1.0), volume=volume)
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass


class CompositeEngine:
    """Merges multiple engines so the picker shows, e.g., the Piper neural
    voice *and* all macOS voices together. Routes synthesis to whichever engine
    owns the requested voice id."""

    def __init__(self, engines: list) -> None:
        if not engines:
            raise EngineError("no engines available")
        self._engines = engines
        self.name = "+".join(e.name for e in engines)
        self._owner: dict[str, object] = {}

    def list_voices(self) -> list[VoiceInfo]:
        merged: list[VoiceInfo] = []
        self._owner.clear()
        for eng in self._engines:
            for v in eng.list_voices():
                self._owner[v.id] = eng
                merged.append(v)
        return merged

    def synthesize(
        self, *, text, voice_id, rate, pitch, volume, fmt, emotion="neutral"
    ):
        if not self._owner:
            self.list_voices()
        eng = self._owner.get(voice_id)
        if eng is None:
            raise EngineError(f"unknown voice {voice_id}")
        kwargs = dict(
            text=text,
            voice_id=voice_id,
            rate=rate,
            pitch=pitch,
            volume=volume,
            fmt=fmt,
        )
        # Only engines that opt in (e.g. Parler) accept an emotion description.
        if getattr(eng, "supports_emotion", False):
            kwargs["emotion"] = emotion
        return eng.synthesize(**kwargs)


def load_engine():
    """Compose every usable engine, most natural first.

    Order: Kokoro (most human) -> Piper (neural) -> macOS say (breadth).
    Force a single engine with VOXFORGE_ENGINE=kokoro|piper|say.
    """
    forced = os.environ.get("VOXFORGE_ENGINE", "").lower()
    if forced == "say":
        return SayEngine()
    if forced == "piper":
        return PiperEngine()
    if forced == "kokoro":
        return KokoroEngine()
    if forced == "mms":
        return MMSEngine()
    if forced == "parler":
        return ParlerEngine()
    if forced == "chatterbox":
        return ChatterboxEngine()
    if forced == "svara":
        return SvaraEngine()

    engines: list = []
    # Order = picker order. Fast engines first so the default voice stays snappy;
    # the HD/Expressive engines (Parler, Chatterbox) are available but never the
    # default. Each is skipped gracefully if its model/service isn't available.
    for ctor in (
        KokoroEngine,
        PiperEngine,
        MMSEngine,
        ParlerEngine,
        SvaraEngine,
        ChatterboxEngine,
    ):
        try:
            engines.append(ctor())
        except EngineError:
            pass
    if platform.system() == "Darwin":
        try:
            engines.append(SayEngine())
        except EngineError:
            pass
    if not engines:
        raise EngineError(
            "No usable engine. Run setup.sh for neural voices, or use macOS."
        )
    return CompositeEngine(engines)
