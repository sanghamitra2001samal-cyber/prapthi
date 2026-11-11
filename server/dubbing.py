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
import re

import idle_models
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

# IndicTrans2 (best Indic quality; auto-used for en->Indic when the model is
# accessible — i.e. once an HF token is cached on the server). Covers Telugu &
# Assamese that M2M-100 lacks.
IT2_LANG = {
    "hi": "hin_Deva", "ta": "tam_Taml", "te": "tel_Telu", "kn": "kan_Knda",
    "ml": "mal_Mlym", "bn": "ben_Beng", "mr": "mar_Deva", "gu": "guj_Gujr",
    "pa": "pan_Guru", "or": "ory_Orya", "ne": "npi_Deva", "ur": "urd_Arab",
    "as": "asm_Beng",
}


def _drop(*names: str):
    """An idle_models unload: forget these module globals. Callers keep their
    own reference while they work, so a running job is never interrupted."""
    def run() -> bool:
        for n in names:
            globals()[n] = None
        return True
    return run


def _get_whisper():
    global _whisper
    idle_models.touch("whisper-small", _drop("_whisper"))
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
    idle_models.touch("stt", _drop("_stt"))
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
    idle_models.touch("m2m100", _drop("_mt", "_mt_tok"))
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


class NoAudioError(ValueError):
    """The upload has no readable audio. Its message is shown to the customer."""
    public = True


def extract_audio(in_path: str, wav_path: str) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-i", in_path, "-vn", "-ac", "1",
                        "-ar", "16000", wav_path], capture_output=True)
    # Until 9 Nov 2026 a failure here passed silently and the job died later on a
    # missing file, showing the customer a server path.
    if r.returncode != 0 or not os.path.exists(wav_path) or os.path.getsize(wav_path) < 2000:
        raise NoAudioError("We couldn't find any sound in this file. Please upload a video or "
                           "audio file with speech in it (MP4, MOV, MP3, WAV, M4A).")


def _get_stt_accurate():
    global _stt_accurate
    idle_models.touch("stt-accurate", _drop("_stt_accurate"))
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


# IndicTrans2 comes as three models, one per direction. Until 9 Nov 2026 the
# models (gated) and IndicTransToolkit were missing on the server, so every
# dub used M2M-100: it turned "बाजार" into Tamil for "sale", wrote "Chennai"
# for "Pune", and has no Telugu at all. Measured that day, IndicTrans2 got all
# of those right and ran 2-3x faster.
_IT2_MODELS = {"en-indic": "ai4bharat/indictrans2-en-indic-dist-200M",
               "indic-en": "ai4bharat/indictrans2-indic-en-dist-200M",
               "indic-indic": "ai4bharat/indictrans2-indic-indic-dist-320M"}
_IT2_LOADED: dict[str, tuple] = {}
_IT2_FAILED: set[str] = set()
IT2_LANG.update({"sa": "san_Deva", "mai": "mai_Deva", "kok": "gom_Deva", "doi": "doi_Deva",
                 "brx": "brx_Deva", "mni": "mni_Beng", "sd": "snd_Arab", "ks": "kas_Arab",
                 "sat": "sat_Olck"})


def _get_it2(direction: str = "en-indic"):
    """(model, tokenizer, processor) for one IndicTrans2 direction, or None if
    it cannot load (no access): the caller falls back to M2M-100. Callers work
    from the returned tuple, so freeing it when idle cannot break a running
    translation."""
    if direction in _IT2_FAILED:
        return None
    idle_models.touch(f"indictrans2:{direction}",
                      lambda: _IT2_LOADED.pop(direction, None) and None)
    got = _IT2_LOADED.get(direction)
    if got is None:
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            from IndicTransToolkit.processor import IndicProcessor
            m = _IT2_MODELS[direction]
            got = (AutoModelForSeq2SeqLM.from_pretrained(m, trust_remote_code=True).eval(),
                   AutoTokenizer.from_pretrained(m, trust_remote_code=True),
                   IndicProcessor(inference=True))
            _IT2_LOADED[direction] = got
            print(f"[dub] IndicTrans2 {direction} loaded")
        except Exception as e:
            print(f"[dub] IndicTrans2 {direction} unavailable ({repr(e)[:80]}); using M2M-100")
            _IT2_FAILED.add(direction)
            return None
    return got


def _it2_translate(it2, texts: list[str], src: str, tgt: str) -> list[str]:
    import torch
    model, tok, ip = it2
    out: list[str] = []
    for i in range(0, len(texts), 8):                 # small batches: CPU, beam 5
        b = ip.preprocess_batch(texts[i:i + 8], src_lang=src, tgt_lang=tgt)
        enc = tok(b, truncation=True, padding="longest", return_tensors="pt", max_length=256)
        with torch.no_grad():
            g = model.generate(**enc, max_length=256, num_beams=5)
        out += ip.postprocess_batch(tok.batch_decode(g, skip_special_tokens=True), lang=tgt)
    return out


# Names inside English text (a shop, a person, a product) must come out as names.
# IndicTrans2 translated the common words in them: "Ganesh Sweets" became
# "गणेश मिठाई", "Sharma Tea Stall" "శర్మ టీ దుకాణం". Writing the name in the
# target script first was worse ("Prapthi AI" -> "प्रेरणा"). What works is the
# model's own placeholder: it was trained to copy <IDn> through untouched, so a
# multi-word Capitalised name rides through as <ID9n> and is put back in Latin,
# which every voice's text preparation then speaks in its own script. Measured
# 9 Nov 2026 on hi/ta/bn/te/mr: 25/25 names kept once the model's own spelling
# of the tag (<आयडी90>, <আইডি90>) is recognised; sentences without a name are
# byte-identical. A tag that does not come back falls back to the plain
# translation of that sentence, so this can never be worse than before.
_NAME = re.compile(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3}\b")
_NOT_NAME = {"The", "A", "An", "I", "We", "You", "Thank", "Please", "Hello", "Hi", "Welcome",
             "Good", "Dear", "Our", "Your", "This", "That", "Meet", "Call", "Visit", "At",
             "To", "In", "On", "Happy", "Merry"}
_NAME_TAG = re.compile(r"[<\[]\s*[^\s\d<>\[\]]{1,6}\s*(9\d)\s*[>\]]")


def _protect_names(text: str) -> tuple[str, dict[int, str]]:
    names: dict[int, str] = {}
    for m in _NAME.finditer(text):
        words = m.group(0).split()
        while words and words[0] in _NOT_NAME:
            words = words[1:]
        if len(words) >= 2 and len(names) < 10:
            name = " ".join(words)
            if name not in names.values():
                names[90 + len(names)] = name
    for key, name in names.items():
        text = text.replace(name, f"<ID{key}>")
    return text, names


def translate(texts: list[str], src: str, tgt: str) -> list[str]:
    """Translate between English and the Indian languages with IndicTrans2,
    and anything else with M2M-100."""
    src = (src or "en").split("-")[0].lower()
    tgt = (tgt or "en").split("-")[0].lower()
    if src == tgt or not texts:
        return list(texts)
    direction = ("en-indic" if src == "en" and tgt in IT2_LANG else
                 "indic-en" if src in IT2_LANG and tgt == "en" else
                 "indic-indic" if src in IT2_LANG and tgt in IT2_LANG else None)
    if direction:
        it2 = _get_it2(direction)
        if it2 is not None:
            code = lambda l: "eng_Latn" if l == "en" else IT2_LANG[l]  # noqa: E731
            if direction != "en-indic":
                return _it2_translate(it2, texts, code(src), code(tgt))
            wrapped = [_protect_names(t) for t in texts]
            out = _it2_translate(it2, [w for w, _ in wrapped], code(src), code(tgt))
            plain = None
            for i, ((_w, names), o) in enumerate(zip(wrapped, out)):
                if not names:
                    continue
                back = _NAME_TAG.sub(lambda m: names.get(int(m.group(1)), m.group(0)), o)
                if all(n in back for n in names.values()) and not _NAME_TAG.search(back):
                    out[i] = back
                else:                       # the model lost a tag: plain translation
                    if plain is None:
                        plain = _it2_translate(it2, list(texts), code(src), code(tgt))
                    out[i] = plain[i]
            return out
    if tgt not in M2M_LANG:
        raise ValueError(f"cannot translate into '{tgt}' (IndicTrans2 unavailable)")
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
