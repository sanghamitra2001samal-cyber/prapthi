"""Dubbing and Audiobook sent every voice to ENGINE, which does not hold the
IndicF5 (HD) voices, so choosing one failed with "unknown voice if5-...".
Route them like Article narration already does. In place; each anchor once."""
import sys

path = sys.argv[1]
s = open(path, encoding="utf-8").read()
if "_engine_or_if5_wav" in s:
    sys.exit("already patched")


def sub(old: str, new: str) -> None:
    global s
    n = s.count(old)
    if n != 1:
        sys.exit(f"anchor found {n}x: {old[:70]!r}")
    s = s.replace(old, new)


sub("""def _run_dub_pipeline(jid: str, in_path: str, ext: str, tgt: str,""",
    """def _engine_or_if5_wav(text: str, voice: str) -> tuple[bytes, str]:
    \"\"\"One WAV take in a library voice, IndicF5 HD voices included (ENGINE
    does not hold those; the studios that only asked ENGINE failed on them).\"\"\"
    if voice.startswith("if5-"):
        ref = _if5_ref(voice)
        if not ref:
            raise EngineError(f"unknown voice {voice}")
        return if5_synth(text, ref[0], ref[1], fmt="wav")
    return ENGINE.synthesize(
        text=text, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")


def _run_dub_pipeline(jid: str, in_path: str, ext: str, tgt: str,""")
sub("""        def tts_fn(text: str) -> str:
            wavb, _m = ENGINE.synthesize(
                text=text, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")
""", """        def tts_fn(text: str) -> str:
            wavb, _m = _engine_or_if5_wav(text, voice)
""")
sub("""        is_hi = hinglish.is_hindi_voice(voice)
        parts = []
        silence = str(BOOK_DIR / f"{jid}_sil.wav")""",
    """        is_hi = hinglish.is_hindi_voice(voice) or voice.startswith("if5")
        parts = []
        silence = str(BOOK_DIR / f"{jid}_sil.wav")""")
sub("""            wavb, _m = ENGINE.synthesize(
                text=t, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")
            wavb, _m = age_voice.apply(wavb, _m, _age, _speech_lang(voice) or "", voice)
            p = str(BOOK_DIR / f"{jid}_p{i}.wav")""",
    """            wavb, _m = _engine_or_if5_wav(t, voice)
            wavb, _m = age_voice.apply(wavb, _m, _age, _speech_lang(voice) or "", voice)
            p = str(BOOK_DIR / f"{jid}_p{i}.wav")""")
open(path, "w", encoding="utf-8").write(s)
print("patched", path)
