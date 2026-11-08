"""AI Dubbing pipeline (self-hosted, API-free) — beat ElevenLabs in India.

video/audio in  ->  Whisper (transcribe + timestamps)
                ->  M2M-100 (translate to target Indian language)
                ->  Parler TTS (re-voice, per segment)
                ->  time-align each line to the original timing
                ->  (optional) Demucs: keep original music bed, replace speech
                ->  mux dubbed audio back into the video

STT: faster-whisper. MT: facebook/m2m100_418M (MIT, commercial-safe, covers most
Indic langs). TTS: the app's Parler engine (passed in as `tts_fn`).
"""

from __future__ import annotations

import os
import subprocess
import tempfile

# M2M-100 language codes for the languages we expose (Telugu/Assamese need
# IndicTrans2 — added later behind an HF token).
M2M_LANG = {
    "hi": "hi", "bn": "bn", "ta": "ta", "mr": "mr", "gu": "gu", "pa": "pa",
    "ml": "ml", "kn": "kn", "or": "or", "ne": "ne", "ur": "ur", "en": "en",
}

_whisper = None
_mt = None
_mt_tok = None
_it2 = _it2_tok = _it2_ip = None
_it2_ok = None  # None=untried, True/False=availability

# IndicTrans2 (best Indic quality; auto-used for en->Indic when the model is
# accessible — i.e. once an HF token is cached on the server). Covers Telugu &
# Assamese that M2M-100 lacks.
IT2_LANG = {
    "hi": "hin_Deva", "ta": "tam_Taml", "te": "tel_Telu", "kn": "kan_Knda",
    "ml": "mal_Mlym", "bn": "ben_Beng", "mr": "mar_Deva", "gu": "guj_Gujr",
    "pa": "pan_Guru", "or": "ory_Orya", "ne": "npi_Deva", "ur": "urd_Arab",
    "as": "asm_Beng",
}


def _get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        ct = "float16" if dev == "cuda" else "int8"
        _whisper = WhisperModel("small", device=dev, compute_type=ct)
    return _whisper


# Speech-to-text for /transcribe (phone answers, short clips). Separate from the dubbing
# model so its size can change without touching dubbing. On the CPU-only VM, "small" with the
# language set answers in ~1.3 s; "large-v3-turbo" is more accurate but ~5.6 s per clip, too
# slow for a live call. Set VOXFORGE_STT_MODEL=large-v3-turbo on a GPU host.
_stt = None
STT_MODEL = os.environ.get("VOXFORGE_STT_MODEL", "small")

# The studio's Speech to Text page, where accuracy matters more than speed.
# Measured on clips of known text (Oct 2026): "small" writes Bengali, Gujarati,
# Marathi, Malayalam and Punjabi in Devanagari, and auto-detects Telugu and
# Kannada as Sinhala. large-v3-turbo with the language given writes the right
# script: Gujarati 5%, Kannada 8%, Bengali 18%, Telugu 20% character errors.
_stt_accurate = None
STT_ACCURATE_MODEL = os.environ.get("VOXFORGE_STT_ACCURATE_MODEL", "large-v3-turbo")


def _get_stt():
    global _stt
    if _stt is None:
        from faster_whisper import WhisperModel
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        ct = "float16" if dev == "cuda" else "int8"
        try:
            _stt = WhisperModel(STT_MODEL, device=dev, compute_type=ct)
        except Exception as e:  # e.g. an older faster-whisper without this model name
            print(f"[stt] {STT_MODEL} unavailable ({e!r}); using the dubbing model")
            _stt = _get_whisper()
    return _stt


def _get_mt():
    global _mt, _mt_tok
    if _mt is None:
        from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        _mt_tok = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
        _mt = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M")
    return _mt, _mt_tok


def _dur(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def extract_audio(in_path: str, wav_path: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-i", in_path, "-vn", "-ac", "1",
                    "-ar", "16000", wav_path], capture_output=True)


def _get_stt_accurate():
    global _stt_accurate
    if _stt_accurate is None:
        from faster_whisper import WhisperModel
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        ct = "float16" if dev == "cuda" else "int8"
        try:
            _stt_accurate = WhisperModel(STT_ACCURATE_MODEL, device=dev, compute_type=ct)
        except Exception as e:  # never leave the page without a model
            print(f"[stt] {STT_ACCURATE_MODEL} unavailable ({e!r}); using {STT_MODEL}")
            _stt_accurate = _get_stt()
    return _stt_accurate


# Spoken Hindi and Urdu are one language to Whisper. Left to guess, large-v3-turbo
# labels Hindi as "ur" and writes it in Urdu script: on 90 s of studio Hindi with
# known text (Nov 2026) it scored 23% character errors guessing, 8% told "hi"
# (small: 20% either way). No dub target or voice takes Urdu script, so read it as Hindi.
_GUESS_AS = {"ur": "hi"}


def _guess_language(model, wav_path: str) -> str | None:
    """One detection on the opening 30 s, so a long file is not re-guessed per window."""
    from faster_whisper import decode_audio
    try:
        audio = decode_audio(wav_path, sampling_rate=16000)[: 30 * 16000]
        lang, _prob, _all = model.detect_language(audio, vad_filter=True)
    except Exception as e:  # silence or an odd file: let transcribe() detect as before
        print(f"[stt] language detection failed: {e!r}")
        return None
    return _GUESS_AS.get(lang, lang)


# Clean Hindi reads far better with the Vakyansh CTC model (fast_stt) than with any
# Whisper, but it falls apart in noise. Character errors, Nov 2026, SYSPIN clips with
# rain mixed in (clean: 24 clips; the rest: 16):
#   noise (true SNR)   clean   30 dB   20 dB   15 dB   10 dB   5 dB
#   Vakyansh           4.6%    5.9%    8.5%    13.4%   24.4%   40.6%
#   large-v3-turbo     8.8%    9.5%    10.3%   12.3%   18.0%   26.4%
# They cross near 17 dB. _estimate_snr read 26 dB at 20 and 21 dB at 15, so files it
# puts at 24 dB or more go to Vakyansh. Calibrated on steady noise only; music unmeasured.
_CTC_MIN_SNR_DB = float(os.environ.get("VOXFORGE_CTC_MIN_SNR_DB", "24"))


def _estimate_snr(audio) -> float:
    """Loudest vs quietest 25 ms frames (90th vs 10th percentile power), in dB.
    Digital silence (edited-in gaps) is skipped so it cannot pass for a clean recording."""
    import numpy as np
    a = np.asarray(audio, dtype=np.float64)
    if a.size < 16000:
        return 0.0
    c = np.concatenate([[0.0], np.cumsum(a * a)])
    starts = np.arange(0, a.size - 400, 160)
    power = (c[starts + 400] - c[starts]) / 400
    power = power[power > 1e-8]                      # below -80 dBFS: digital silence
    if power.size < 20:
        return 0.0
    return float(10 * np.log10(np.percentile(power, 90) / np.percentile(power, 10)))


def _ctc_hindi_segments(audio) -> list[dict] | None:
    """Hindi via fast_stt's Vakyansh worker. It returns text without timings, so speech
    is first cut at pauses (at most 12 s a piece) and each piece read on its own, which
    keeps the start/end times dubbing aligns to. None if the worker cannot be used."""
    import numpy as np
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    import fast_stt
    spans = get_speech_timestamps(audio, VadOptions(
        max_speech_duration_s=12, min_silence_duration_ms=500, speech_pad_ms=200))
    segs = []
    try:
        for sp in spans:
            piece = np.clip(audio[sp["start"]:sp["end"]], -1.0, 1.0)
            text = fast_stt.transcribe_pcm((piece * 32767).astype("<i2").tobytes(), 16000)
            if text:
                segs.append({"start": sp["start"] / 16000, "end": sp["end"] / 16000, "text": text})
    except Exception as e:  # worker died or timed out: the caller uses Whisper instead
        print(f"[stt] Vakyansh unavailable ({e!r}); using Whisper")
        return None
    return segs


def transcribe(wav_path: str, language: str | None = None, vad: bool = True,
               stt: bool = False, accurate: bool = False,
               clean_hindi_ctc: bool = False) -> tuple[list[dict], str]:
    """Return ([{start,end,text}], language).

    language: a Whisper code ("hi", "en", ...) to skip auto-detection, which misreads short
    Hindi answers as English. vad=False keeps very short replies ("हाँ") that the silence
    filter would drop; use it for clips already trimmed to the utterance. stt=True uses the
    /transcribe model instead of the dubbing one; accurate=True the larger model the studio's
    Speech to Text page uses, which then detects the language itself (see _GUESS_AS).
    clean_hindi_ctc=True reads clean Hindi with Vakyansh instead (see _CTC_MIN_SNR_DB); its
    text has no punctuation, so only callers that don't show it to people should ask.
    """
    model = _get_stt_accurate() if accurate else (_get_stt() if stt else _get_whisper())
    if accurate and not language:
        language = _guess_language(model, wav_path)
    if clean_hindi_ctc and language == "hi":
        from faster_whisper import decode_audio
        audio = decode_audio(wav_path, sampling_rate=16000)
        snr = _estimate_snr(audio)
        if snr >= _CTC_MIN_SNR_DB:
            segs = _ctc_hindi_segments(audio)
            if segs:
                print(f"[stt] Hindi at ~{snr:.0f} dB: Vakyansh")
                return segs, "hi"
        print(f"[stt] Hindi at ~{snr:.0f} dB: Whisper")
    segments, info = model.transcribe(wav_path, vad_filter=vad, beam_size=5,
                                      language=language or None)
    segs = []
    for s in segments:
        t = (s.text or "").strip()
        if t:
            segs.append({"start": float(s.start), "end": float(s.end), "text": t})
    return segs, info.language


def _get_it2():
    """Lazy-load IndicTrans2 (en->Indic). Returns None if not accessible
    (e.g. no HF token) — caller falls back to M2M-100."""
    global _it2, _it2_tok, _it2_ip, _it2_ok
    if _it2_ok is False:
        return None
    if _it2 is None:
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            from IndicTransToolkit.processor import IndicProcessor
            M = "ai4bharat/indictrans2-en-indic-dist-200M"
            _it2_tok = AutoTokenizer.from_pretrained(M, trust_remote_code=True)
            _it2 = AutoModelForSeq2SeqLM.from_pretrained(M, trust_remote_code=True)
            _it2_ip = IndicProcessor(inference=True)
            _it2_ok = True
            print("[dub] IndicTrans2 loaded (best Indic quality)")
        except Exception as e:
            print(f"[dub] IndicTrans2 unavailable ({repr(e)[:60]}); using M2M-100")
            _it2_ok = False
            return None
    return _it2


def translate(texts: list[str], src: str, tgt: str) -> list[str]:
    # Prefer IndicTrans2 for English -> Indic (best quality + Telugu/Assamese).
    if (src or "en").startswith("en") and tgt in IT2_LANG and _get_it2() is not None:
        import torch
        b = _it2_ip.preprocess_batch(texts, src_lang="eng_Latn", tgt_lang=IT2_LANG[tgt])
        enc = _it2_tok(b, truncation=True, padding="longest", return_tensors="pt")
        with torch.no_grad():
            g = _it2.generate(**enc, max_length=256, num_beams=5)
        dec = _it2_tok.batch_decode(g, skip_special_tokens=True)
        return _it2_ip.postprocess_batch(dec, lang=IT2_LANG[tgt])
    if tgt not in M2M_LANG:
        raise ValueError(
            f"target '{tgt}' needs IndicTrans2 (add an HF token to enable it)")
    import torch
    model, tok = _get_mt()
    tok.src_lang = M2M_LANG.get(src, "en")
    out = []
    bos = tok.get_lang_id(M2M_LANG[tgt])
    for t in texts:
        enc = tok(t, return_tensors="pt", truncation=True, max_length=256)
        with torch.no_grad():
            g = model.generate(**enc, forced_bos_token_id=bos, max_length=256,
                               num_beams=4)
        out.append(tok.batch_decode(g, skip_special_tokens=True)[0])
    return out


def _atempo_chain(factor: float) -> list[str]:
    """ffmpeg atempo only accepts 0.5–2.0; chain for larger factors."""
    factor = max(0.25, min(factor, 4.0))
    out = []
    while factor > 2.0:
        out.append("atempo=2.0"); factor /= 2.0
    while factor < 0.5:
        out.append("atempo=0.5"); factor /= 0.5
    out.append(f"atempo={factor:.4f}")
    return out


def assemble_dub(segments: list[dict], tts_fn, out_wav: str) -> str:
    """segments: [{start,end,text_tgt}]. tts_fn(text)->wav path (any sr/mono).
    Each line is time-stretched to fit its original slot and placed at its start
    time, then everything is mixed onto one track."""
    work = tempfile.mkdtemp()
    placed = []
    try:
        for i, s in enumerate(segments):
            txt = (s.get("text_tgt") or "").strip()
            if not txt:
                continue
            raw = tts_fn(txt)                       # synth target-language line
            if not raw or not os.path.exists(raw):
                continue
            slot = max(0.4, float(s["end"]) - float(s["start"]))
            d = _dur(raw)
            fitted = os.path.join(work, f"f{i}.wav")
            af = []
            if d > 0:
                af += _atempo_chain(d / slot)       # speed to fit the slot
            delay = int(float(s["start"]) * 1000)
            af.append(f"adelay={delay}|{delay}")
            subprocess.run(["ffmpeg", "-y", "-i", raw, "-af", ",".join(af),
                            fitted], capture_output=True)
            if os.path.exists(fitted):
                placed.append(fitted)
        if not placed:
            raise RuntimeError("no dubbed segments produced")
        # mix all placed (delayed) segments onto one track
        cmd = ["ffmpeg", "-y"]
        for p in placed:
            cmd += ["-i", p]
        fc = "".join(f"[{i}:a]" for i in range(len(placed)))
        fc += f"amix=inputs={len(placed)}:duration=longest:normalize=0,dynaudnorm=f=200[a]"
        cmd += ["-filter_complex", fc, "-map", "[a]", "-ar", "44100", out_wav]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_wav
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def mux_audio_to_video(video_in: str, audio_in: str, out_path: str,
                       keep_bg: float = 0.0) -> str:
    """Replace the video's audio with the dubbed track (optionally keeping a bit
    of the original audio as a faint bed via keep_bg 0..1)."""
    if keep_bg > 0:
        fc = (f"[0:a]volume={keep_bg}[bg];[1:a]volume=1.0[v];"
              f"[bg][v]amix=inputs=2:duration=longest:normalize=0[a]")
        cmd = ["ffmpeg", "-y", "-i", video_in, "-i", audio_in,
               "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
               "-c:v", "copy", "-shortest", out_path]
    else:
        cmd = ["ffmpeg", "-y", "-i", video_in, "-i", audio_in,
               "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-shortest", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
