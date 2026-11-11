"""Add child / grandparent voices (age_voice.py) to an app.py, in place.
Each anchor must occur exactly once, or nothing is written."""
import sys

path = sys.argv[1]
s = open(path, encoding="utf-8").read()
if "age_voice" in s:
    sys.exit("already patched")


def sub(old: str, new: str) -> None:
    global s
    n = s.count(old)
    if n != 1:
        sys.exit(f"anchor found {n}x: {old[:70]!r}")
    s = s.replace(old, new)


sub("import voice_names\n", "import voice_names\nimport age_voice\n")

# /voices: list them (named by age_voice, not by the catalogue-wide pass)
sub("""    # Append this user's private cloned voices (powered by Chatterbox).
""", """    # Child and grandparent voices, each made from an adult voice listed above.
    data.extend(age_voice.catalogue({str(v["id"]): str(v["lang"]) for v in data}))
    # Append this user's private cloned voices (powered by Chatterbox).
""")
sub("""          str(v.get("gender") or "female")) for v in data])""",
    """          str(v.get("gender") or "female")) for v in data
         if not age_voice.split(str(v["id"]))[1]])""")
sub("""    _PICKER_NAMES.update(_named)
""", """    _PICKER_NAMES.update(_named)
    _PICKER_NAMES.update({str(v["id"]): str(v["name"]) for v in data
                          if age_voice.split(str(v["id"]))[1]})
""")

# /synthesize + /preview: everything downstream sees the adult voice
sub("""    voice_id = str(body.get("voiceId", "")).strip()
    if not voice_id:
        return JSONResponse({"error": "voiceId required"}, status_code=400)
""", """    voice_id = str(body.get("voiceId", "")).strip()
    if not voice_id:
        return JSONResponse({"error": "voiceId required"}, status_code=400)
    # Child / grandparent voice: render its adult voice, reshape at the end.
    req_vid = voice_id
    voice_id, _age = age_voice.split(voice_id)
""")
sub("""            name = _PICKER_NAMES.get(voice_id, name)
""", """            name = _PICKER_NAMES.get(req_vid, _PICKER_NAMES.get(voice_id, name))
""")
sub("""    # Emotion prosody: scale the user's sliders by the emotion's feel factors
""", """    if _age:
        cache_vid += f"~{_age}.{age_voice.VERSION}"

    # Emotion prosody: scale the user's sliders by the emotion's feel factors
""")
sub("""    async def _render(t_: str, emo_: str, r_: float, p_: float, v_: float,
                      fmt_: str):
        \"\"\"Run the right engine for this voice (one feeling, one chunk).\"\"\"
""", """    async def _render(t_: str, emo_: str, r_: float, p_: float, v_: float,
                      fmt_: str):
        \"\"\"One feeling, one chunk, in the voice asked for (aged if it is one).\"\"\"
        audio, mime = await _render_base(t_, emo_, r_, p_, v_, fmt_)
        if _age:
            audio, mime = await run_in_threadpool(
                age_voice.apply, audio, mime, _age, _voice_owner(voice_id)[1], voice_id)
            if fmt_ != "wav":
                audio, mime = await run_in_threadpool(_wav_to_mp3, audio)
        return audio, mime

    async def _render_base(t_: str, emo_: str, r_: float, p_: float, v_: float,
                           fmt_: str):
        \"\"\"Run the right engine for this voice (one feeling, one chunk).\"\"\"
""")

# Dubbing
sub("""    \"\"\"Heavy dubbing work (runs in a threadpool).\"\"\"
    import tempfile as _tf
""", """    \"\"\"Heavy dubbing work (runs in a threadpool).\"\"\"
    import tempfile as _tf
    voice, _age = age_voice.split(voice)
""")
sub("""        def tts_fn(text: str) -> str:
            wavb, _m = ENGINE.synthesize(
                text=text, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")
""", """        def tts_fn(text: str) -> str:
            wavb, _m = ENGINE.synthesize(
                text=text, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")
            wavb, _m = age_voice.apply(wavb, _m, _age, tgt, voice)
""")

# Audiobook
sub("""def _run_audiobook(jid: str, text: str, voice: str, gap_ms: int) -> None:
    import tempfile as _tf
""", """def _run_audiobook(jid: str, text: str, voice: str, gap_ms: int) -> None:
    import tempfile as _tf
    voice, _age = age_voice.split(voice)
""")
sub("""            wavb, _m = ENGINE.synthesize(
                text=t, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")
            p = str(BOOK_DIR / f"{jid}_p{i}.wav")
""", """            wavb, _m = ENGINE.synthesize(
                text=t, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")
            wavb, _m = age_voice.apply(wavb, _m, _age, _speech_lang(voice) or "", voice)
            p = str(BOOK_DIR / f"{jid}_p{i}.wav")
""")

# Article narration (AudioNative)
sub("""def _run_audionative(aid: str, text: str, voice: str, title: str, owner: str) -> None:
    import tempfile as _tf
""", """def _run_audionative(aid: str, text: str, voice: str, title: str, owner: str) -> None:
    import tempfile as _tf
    voice, _age = age_voice.split(voice)
""")
sub("""                wavb, _m = ENGINE.synthesize(text=t, voice_id=voice, rate=1.0,
                                             pitch=1.0, volume=1.0, fmt="wav")
            p = str(AN_DIR / f"{aid}_p{i}.wav")
""", """                wavb, _m = ENGINE.synthesize(text=t, voice_id=voice, rate=1.0,
                                             pitch=1.0, volume=1.0, fmt="wav")
            if wavb:
                wavb, _m = age_voice.apply(wavb, _m, _age, _speech_lang(voice) or "", voice)
            p = str(AN_DIR / f"{aid}_p{i}.wav")
""")

# Ads
sub("""def _ads_synth(text: str, voice: str) -> bytes:
    if voice.startswith("if5-"):
        ref = _if5_ref(voice)
        if ref:
            a, _m = if5_synth(text, ref[0], ref[1], fmt="mp3")
            return a
    a, _m = ENGINE.synthesize(text=text, voice_id=voice, rate=1.0, pitch=1.0,
                              volume=1.0, fmt="mp3")
    return a
""", """def _ads_synth(text: str, voice: str) -> bytes:
    voice, _age = age_voice.split(voice)
    fmt = "wav" if _age else "mp3"
    a = b""
    if voice.startswith("if5-"):
        ref = _if5_ref(voice)
        if ref:
            a, _m = if5_synth(text, ref[0], ref[1], fmt=fmt)
    if not a:
        a, _m = ENGINE.synthesize(text=text, voice_id=voice, rate=1.0, pitch=1.0,
                                  volume=1.0, fmt=fmt)
    if _age:
        a, _m = age_voice.apply(a, _m, _age, _speech_lang(voice) or "", voice)
        a, _m = _wav_to_mp3(a)
    return a
""")

open(path, "w", encoding="utf-8").write(s)
print("patched", path)
