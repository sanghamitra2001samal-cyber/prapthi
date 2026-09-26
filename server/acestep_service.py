"""Isolated ACE-Step microservice (Apache-2.0 — API-free full-song generation).

Runs in its own venv (~/ace, torch 2.6) so its deps don't touch the main app.
Generates a complete song *with sung vocals* from a style prompt + lyrics.

Endpoints:
  GET  /health -> {status, device, loaded}
  POST /song   -> {prompt, lyrics, duration, infer_step?} => audio/wav

Replaces the old MusicGen+TTS approach for EmotionSong.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Reduce CUDA fragmentation so ACE-Step coexists with the TTS models.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
from acestep.pipeline_ace_step import ACEStepPipeline

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_LOCK = threading.Lock()  # one GPU — serialize generation
_PIPE = None
_LOADED = threading.Event()


def _get_pipe():
    global _PIPE
    if _PIPE is None:
        # Resident (no cpu_offload) for speed (~10GB, ~10s/song). Fits on the
        # 24GB L4 alongside Chatterbox+Parler now that the warm-up no longer
        # double-loads (it holds _LOCK) and expandable_segments cuts fragmentation.
        _PIPE = ACEStepPipeline(dtype="bfloat16", cpu_offload=False, quantized=False)
        _LOADED.set()
    return _PIPE


def _warm():
    """Force the checkpoint to fully load at boot (a tiny throwaway generation),
    so the first real user request is fast instead of triggering a long lazy
    load/download."""
    try:
        import glob

        # Hold the lock during warm so an incoming request can't trigger a
        # second concurrent checkpoint load (which caused OOM).
        with _LOCK:
            pipe = _get_pipe()
            out = tempfile.mktemp(suffix=".wav")
            pipe(
                format="wav", audio_duration=10, prompt="pop",
                lyrics="[verse]\nla la la", infer_step=4, guidance_scale=7,
                save_path=out,
            )
            for p in [out, *glob.glob(out.replace(".wav", "*"))]:
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
        _LOADED.set()
        print(f"[acestep] warmed (checkpoint loaded) on {DEVICE}", flush=True)
    except Exception as e:  # pragma: no cover
        print(f"[acestep] warm load failed: {e!r}", flush=True)


def _generate(
    prompt: str,
    lyrics: str,
    duration: float,
    infer_step: int,
    ref_audio_path: str | None = None,
    ref_strength: float = 0.5,
    seed: int | None = None,
) -> bytes:
    duration = max(10.0, min(float(duration or 30), 180.0))
    with _LOCK:
        pipe = _get_pipe()
        out = tempfile.mktemp(suffix=".wav")
        try:
            kwargs = dict(
                format="wav",
                audio_duration=duration,
                prompt=prompt or "pop, instrumental",
                lyrics=lyrics or "",
                infer_step=int(infer_step or 27),
                guidance_scale=15.0,
                save_path=out,
            )
            if seed is not None:
                kwargs["manual_seeds"] = [int(seed)]
            # Sing in a reference voice (audio-to-audio conditioning).
            if ref_audio_path and os.path.exists(ref_audio_path):
                kwargs["audio2audio_enable"] = True
                kwargs["ref_audio_input"] = ref_audio_path
                kwargs["ref_audio_strength"] = float(ref_strength)
            pipe(**kwargs)
            # ACE-Step may append an index; find the produced file.
            path = out
            if not os.path.exists(path):
                import glob

                cands = glob.glob(out.replace(".wav", "*")) or glob.glob(
                    tempfile.gettempdir() + "/*.wav"
                )
                path = cands[0] if cands else out
            with open(path, "rb") as f:
                return f.read()
        finally:
            for p in {out, locals().get("path", out)}:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
            # Release cached GPU memory so the TTS models have room afterwards.
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass


_STEM_LOCK = threading.Lock()


def _stems(audio_path: str, out_dir: str, sid: str) -> dict:
    """Split a finished song into stems with Demucs (CPU, to avoid GPU contention
    with ACE-Step). Outputs vocals/drums/bass/other + an instrumental (karaoke)
    mix as MP3 named <sid>_<stem>.mp3 directly in out_dir."""
    with _STEM_LOCK:
        os.makedirs(out_dir, exist_ok=True)
        work = tempfile.mkdtemp()
        try:
            subprocess.run(
                [sys.executable, "-m", "demucs", "-d", "cpu", "--mp3",
                 "-o", work, audio_path],
                check=True, capture_output=True,
            )
            base = glob.glob(os.path.join(work, "htdemucs", "*"))
            if not base:
                raise RuntimeError("demucs produced no output")
            base = base[0]
            paths = {}
            for name in ("vocals", "drums", "bass", "other"):
                src = os.path.join(base, f"{name}.mp3")
                if os.path.exists(src):
                    dst = os.path.join(out_dir, f"{sid}_{name}.mp3")
                    shutil.move(src, dst)
                    paths[name] = dst
            # instrumental (karaoke) = drums + bass + other
            ins = [paths[n] for n in ("drums", "bass", "other") if n in paths]
            if len(ins) >= 2:
                inst = os.path.join(out_dir, f"{sid}_instrumental.mp3")
                cmd = ["ffmpeg", "-y"]
                for p in ins:
                    cmd += ["-i", p]
                fc = "".join(f"[{i}:a]" for i in range(len(ins)))
                fc += f"amix=inputs={len(ins)}:duration=longest:normalize=0"
                cmd += ["-filter_complex", fc, "-b:a", "192k", inst]
                subprocess.run(cmd, check=True, capture_output=True)
                paths["instrumental"] = inst
            return paths
        finally:
            shutil.rmtree(work, ignore_errors=True)


_SFX_PIPE = None
_SFX_LOCK = threading.Lock()


def _sfx(prompt: str, duration: float) -> bytes:
    """Generate a sound effect / ambient audio from a text prompt (AudioLDM2)."""
    global _SFX_PIPE
    import numpy as np
    import scipy.io.wavfile as wavfile

    with _SFX_LOCK:
        if _SFX_PIPE is None:
            from diffusers import AudioLDM2Pipeline
            p = AudioLDM2Pipeline.from_pretrained(
                "cvssp/audioldm2",
                torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32)
            _SFX_PIPE = p.to(DEVICE)
        dur = max(2.0, min(float(duration or 5), 30.0))
        gen = torch.Generator(DEVICE).manual_seed(0)
        audio = _SFX_PIPE(
            prompt or "ambient sound", num_inference_steps=180,
            audio_length_in_s=dur, num_waveforms_per_prompt=1, generator=gen,
        ).audios[0]
        out = tempfile.mktemp(suffix=".wav")
        try:
            pcm = np.clip(audio, -1, 1)
            wavfile.write(out, 16000, (pcm * 32767).astype(np.int16))
            with open(out, "rb") as f:
                data = f.read()
        finally:
            if os.path.exists(out):
                os.unlink(out)
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        return data


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok", "device": DEVICE, "loaded": _LOADED.is_set()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/stems":
                paths = _stems(body["audio_path"], body["out_dir"], body["sid"])
                return self._json(200, {"paths": paths})
            if self.path == "/sfx":
                audio = _sfx(body.get("prompt", ""), body.get("duration", 5))
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(audio)))
                self.end_headers()
                self.wfile.write(audio)
                return
            if self.path != "/song":
                return self._json(404, {"error": "not found"})
            audio = _generate(
                body.get("prompt", ""),
                body.get("lyrics", ""),
                body.get("duration", 30),
                body.get("infer_step", 27),
                ref_audio_path=body.get("ref_audio_input") or None,
                ref_strength=body.get("ref_audio_strength", 0.5),
                seed=body.get("seed"),
            )
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        except Exception as e:  # pragma: no cover
            self._json(500, {"error": repr(e)[:300]})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("ACESTEP_PORT", "8003"))
    threading.Thread(target=_warm, daemon=True).start()
    print(f"[acestep] serving on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
