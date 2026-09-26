"""EmotionSong pipeline (API-free): script -> emotion -> lyrics -> song.

All self-hosted:
  * Emotion detection: a small HuggingFace classifier (CPU, lazy-loaded).
  * Lyrics: deterministic structuring of the script into verse/chorus/etc.
  * Beat: MusicGen microservice (:8002).
  * Vocals: the app's existing TTS engine reads the lyrics with emotion.
  * Mix: ffmpeg overlays ducked beat under the vocals -> MP3.

The heavy orchestration (job + DB) lives in app.py; this module is the toolbox.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.request
import wave

MUSICGEN_URL = os.environ.get("MUSICGEN_URL", "http://127.0.0.1:8002")
ACESTEP_URL = os.environ.get("ACESTEP_URL", "http://127.0.0.1:8003")

# ACE-Step style tags built from genre + emotion + vocals.
_GENRE_TAGS = {
    "pop": "pop", "bollywood": "bollywood, indian, filmi",
    "lofi": "lo-fi, chill, mellow", "lo-fi": "lo-fi, chill, mellow",
    "hiphop": "hip hop, rap beat", "hip-hop": "hip hop, rap beat",
    "rock": "rock, electric guitar", "edm": "edm, electronic, dance",
    "rnb": "r&b, soul, smooth", "classical": "indian classical",
}
_EMO_TAGS = {
    "happy": "happy, upbeat, bright", "sad": "sad, emotional, slow ballad",
    "romantic": "romantic, warm, tender", "motivational": "uplifting, powerful, anthemic",
    "angry": "intense, aggressive, hard", "fear": "dark, tense, cinematic",
    "nostalgic": "nostalgic, wistful", "neutral": "melodic",
    "excited": "energetic, high energy", "calm": "calm, gentle, soft",
}
_VOCAL_TAGS = {
    "female": "female vocals", "male": "male vocals",
    "duet": "duet, male and female vocals",
}
# Mood (alias of emotion words) — explicit list for the UI.
_MOOD_TAGS = {
    **_EMO_TAGS,
    "dreamy": "dreamy, ethereal, atmospheric",
    "dark": "dark, moody, cinematic",
    "epic": "epic, cinematic, powerful",
    "chill": "chill, relaxed, laid-back",
    "party": "party, danceable, high energy",
}
# Singer style → vocal-delivery tags.
_SINGER_STYLE = {
    "": "", "auto": "",
    "soulful": "soulful, emotive delivery",
    "powerful": "powerful belting, strong vocals",
    "soft": "soft, breathy, gentle vocals",
    "raspy": "raspy, husky vocals",
    "smooth": "smooth, melodic vocals",
    "rap": "rap delivery, rhythmic flow",
    "classical": "classical trained vocals, ornamented",
    "autotune": "modern autotuned vocals",
}
# Language → ACE-Step language hint (lyrics carry the actual script).
_LANG_TAGS = {
    "en": "", "hi": "Hindi language", "te": "Telugu language",
    "ta": "Tamil language", "pa": "Punjabi language",
    "hinglish": "Hindi and English mixed (Hinglish) lyrics",
    "mixed": "mixed language lyrics",
}

# Per-language singing-quality descriptors. Indian languages get authentic
# playback-style vocal tags so ACE-Step sings with native diction, emotion and
# ornamentation instead of an accented/foreign delivery.
_LANG_SINGING = {
    "hi": ("authentic Hindi vocals, clear native Hindi diction, expressive "
           "Bollywood playback singing, emotive melodious voice, natural "
           "Indian pronunciation, soulful vocal ornamentation"),
    "hinglish": ("natural Hindi-English vocals, clear diction, expressive "
                 "Bollywood playback singing, emotive melodious voice"),
    "te": ("authentic Telugu vocals, clear native diction, expressive "
           "melodious South-Indian playback singing"),
    "ta": ("authentic Tamil vocals, clear native diction, expressive "
           "melodious South-Indian playback singing"),
    "pa": ("authentic Punjabi vocals, clear native diction, energetic "
           "expressive singing"),
}

# Professional music-theory descriptors per mood: (scale/tonality, chord
# progression feel, dynamics, articulation). These are universal — the notes
# don't change with language — so ACE-Step composes a musically coherent
# arrangement regardless of the lyric language. Roman numerals describe the
# harmonic feel the model should lean toward.
_MOOD_MUSIC = {
    "happy":        ("major key", "I-V-vi-IV chord progression", "bright dynamics", "lively articulation"),
    "sad":          ("minor key", "vi-IV-I-V progression", "soft dynamics", "smooth legato phrasing"),
    "romantic":     ("warm major key", "ii-V-I progression", "gentle dynamics", "tender legato vocals"),
    "motivational": ("major key", "IV-I-V anthemic progression", "building crescendo", "strong accented phrasing"),
    "angry":        ("minor key", "driving power-chord progression", "loud dynamics", "hard-hitting articulation"),
    "fear":         ("minor key", "tense chromatic harmony", "dramatic swells", "staccato tension"),
    "nostalgic":    ("major key", "I-vi-IV-V progression", "soft dynamics", "wistful legato"),
    "dreamy":       ("lush major7 harmony", "floating chord pads", "soft dynamics", "airy legato"),
    "dark":         ("minor key", "brooding chromatic harmony", "dynamic swells", "heavy phrasing"),
    "epic":         ("minor key", "orchestral build progression", "fortissimo crescendos", "marcato phrasing"),
    "chill":        ("mellow major7 harmony", "smooth ii-V progression", "relaxed dynamics", "laid-back legato"),
    "party":        ("major key", "four-on-the-floor groove", "high-energy dynamics", "punchy articulation"),
    "excited":      ("major key", "energetic progression", "high dynamics", "punchy articulation"),
    "calm":         ("major key", "gentle progression", "soft dynamics", "smooth legato"),
    "neutral":      ("balanced tonality", "melodic chord progression", "even dynamics", "natural phrasing"),
}

# Genre → time signature / rhythmic feel.
_GENRE_METER = {
    "pop": "4/4 time", "bollywood": "4/4 time", "lofi": "4/4 laid-back swing",
    "lo-fi": "4/4 laid-back swing", "hiphop": "4/4 boom-bap groove",
    "hip-hop": "4/4 boom-bap groove", "rock": "4/4 driving beat",
    "edm": "4/4 four-on-the-floor", "rnb": "4/4 swung groove",
    "classical": "free-flowing meter",
}

# --------------------------------------------------------------------------- #
# Instrument arrangement engine
# --------------------------------------------------------------------------- #
# ACE-Step is prompt-conditioned (it renders one mixed track, not per-instrument
# stems), but it strongly honours named instruments. We auto-pick a tasteful
# palette per genre, then layer mood + language-specific colours on top. A
# handful of well-chosen instruments works far better than naming dozens.
_GENRE_INSTRUMENTS = {
    "pop": ["electric piano", "synth pad", "electric bass", "drum kit", "claps"],
    "bollywood": ["harmonium", "tabla", "dhol", "string ensemble", "bansuri flute", "acoustic guitar"],
    "lofi": ["electric piano", "soft drum kit", "sub bass", "ambient pads", "vinyl crackle"],
    "lo-fi": ["electric piano", "soft drum kit", "sub bass", "ambient pads", "vinyl crackle"],
    "hiphop": ["808 bass", "electronic drum machine", "hi-hats", "claps", "synth lead"],
    "hip-hop": ["808 bass", "electronic drum machine", "hi-hats", "claps", "synth lead"],
    "rock": ["electric guitar", "lead guitar", "electric bass", "drum kit"],
    "edm": ["synth lead", "synth pad", "808 bass", "electronic drum machine", "arpeggiator", "riser FX"],
    "rnb": ["electric piano", "sub bass", "smooth drum kit", "synth pads", "backing vocals"],
    "classical": ["sitar", "tabla", "tanpura", "bansuri", "sarangi"],
}
# Mood adds emotional colour instruments on top of the genre base.
_MOOD_INSTRUMENTS = {
    "epic": ["full orchestra", "epic drums", "timpani", "brass ensemble", "choir"],
    "dreamy": ["ambient pads", "harp", "celesta"],
    "dark": ["cello", "low brass", "cinematic percussion"],
    "fear": ["cello", "cinematic percussion", "reverse FX"],
    "sad": ["solo violin", "cello", "grand piano"],
    "romantic": ["string ensemble", "grand piano", "bansuri flute"],
    "party": ["brass ensemble", "claps", "synth lead"],
    "nostalgic": ["acoustic guitar", "grand piano"],
    "motivational": ["epic drums", "brass ensemble", "string ensemble"],
    "calm": ["ambient pads", "acoustic guitar"],
}
# Indian-language overlays add authentic regional textures.
_LANG_INSTRUMENTS = {
    "hi": ["tabla", "bansuri flute"],
    "te": ["mridangam", "veena"],
    "ta": ["mridangam", "veena"],
    "pa": ["dhol", "tumbi"],
    "hinglish": ["tabla", "dhol"],
}


def instrument_palette(
    genre: str, mood: str, language: str = "en",
    explicit: list[str] | None = None, limit: int = 8,
) -> list[str]:
    """Pick the instrument arrangement. An explicit user selection wins; we top
    it up with sensible genre/mood/language picks (deduped, capped)."""
    picks: list[str] = []

    def add(items):
        for it in items:
            it = (it or "").strip().lower()
            if it and it not in picks:
                picks.append(it)

    if explicit:
        add(explicit)
    add(_GENRE_INSTRUMENTS.get((genre or "pop").lower(), _GENRE_INSTRUMENTS["pop"]))
    add(_MOOD_INSTRUMENTS.get((mood or "").lower(), []))
    add(_LANG_INSTRUMENTS.get((language or "en").lower(), []))
    return picks[:limit]


def song_prompt(
    genre: str,
    mood: str,
    vocals: str,
    singer_style: str = "",
    bpm: int | None = None,
    musical_key: str = "",
    language: str = "en",
    instruments: list[str] | None = None,
) -> str:
    g = (genre or "pop").lower()
    m = (mood or "neutral").lower()
    parts = [
        _GENRE_TAGS.get(g, "pop"),
        _VOCAL_TAGS.get((vocals or "female").lower(), "female vocals"),
        _MOOD_TAGS.get(m, "melodic"),
    ]
    style = _SINGER_STYLE.get((singer_style or "").lower(), "")
    if style:
        parts.append(style)
    lang = _LANG_TAGS.get((language or "en").lower(), "")
    if lang:
        parts.append(lang)
    sing = _LANG_SINGING.get((language or "en").lower(), "")
    if sing:
        parts.append(sing)

    # Universal music-theory layer: scale, chords, dynamics, articulation, meter.
    scale, chords, dynamics, artic = _MOOD_MUSIC.get(m, _MOOD_MUSIC["neutral"])
    key_l = (musical_key or "").lower()
    if "minor" in key_l:           # an explicit key wins over the mood default
        scale = "minor key"
    elif "major" in key_l:
        scale = "major key"
    parts += [scale, chords, dynamics, artic, _GENRE_METER.get(g, "4/4 time")]

    # Instrument arrangement — auto-selected palette (+ any explicit picks).
    palette = instrument_palette(g, m, (language or "en").lower(), instruments)
    if palette:
        parts.append("featuring " + ", ".join(palette))

    if bpm:
        try:
            parts.append(f"{int(bpm)} bpm")
        except (TypeError, ValueError):
            pass
    if musical_key:
        parts.append(f"key of {musical_key}")
    parts.append(
        "catchy memorable melody, rich layered arrangement, tight rhythm section, "
        "instruments supporting the vocals, clean EQ, smooth compression, "
        "tasteful reverb and delay, wide stereo image, balanced studio mix, "
        "mastered, in-tune expressive lead vocals, professional studio production"
    )
    return ", ".join(p for p in parts if p)


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def prepare_song_lyrics(lyrics: str, language: str) -> str:
    """For Hindi/Hinglish songs, convert romanized Hindi to Devanagari so the
    model sings with native pronunciation. Lines already in Devanagari (or other
    languages) are left untouched."""
    import hinglish

    lang = (language or "en").lower()
    if lang not in ("hi", "hinglish"):
        return lyrics
    out = []
    for ln in lyrics.splitlines():
        # keep section tags ([verse] etc.) and already-Devanagari lines as-is
        if ln.strip().startswith("[") or _DEVANAGARI.search(ln):
            out.append(ln)
        else:
            out.append(hinglish.to_devanagari(ln))
    return "\n".join(out)


def lyrics_for_acestep(lyrics: str) -> str:
    """Normalize our [Verse 1]/[Chorus] structure to ACE-Step's lowercase tags
    and drop the parenthetical title line."""
    out = []
    for ln in lyrics.splitlines():
        s = ln.strip()
        if not s or (s.startswith("(") and s.endswith(")")):
            continue
        m = re.match(r"^\[\s*([A-Za-z]+)", s)
        if m:
            out.append(f"[{m.group(1).lower()}]")
        else:
            out.append(s)
    return "\n".join(out)


def acestep_song(
    prompt: str,
    lyrics: str,
    duration: float,
    infer_step: int = 27,
    ref_audio_path: str | None = None,
    ref_strength: float = 0.5,
    seed: int | None = None,
) -> bytes:
    payload = {
        "prompt": prompt, "lyrics": lyrics, "duration": duration,
        "infer_step": infer_step,
    }
    if ref_audio_path:
        payload["ref_audio_input"] = ref_audio_path
        payload["ref_audio_strength"] = ref_strength
    if seed is not None:
        payload["seed"] = seed
    req = urllib.request.Request(
        ACESTEP_URL + "/song", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        return r.read()


def acestep_stems(audio_path: str, out_dir: str, sid: str) -> dict:
    """Split audio into stems with Demucs, on this box. Returns {stem: path}.

    The ACE-Step service also exposes /stems, but its API takes a *file path* —
    with the model server on another host that path does not exist there. Demucs
    is deliberately CPU-only anyway (it must not contend with the GPU), so run it
    locally and keep the same contract.
    """
    import glob as _glob
    import shutil as _shutil
    import subprocess as _sp
    import tempfile as _tf

    py = os.environ.get("DEMUCS_PY", os.path.expanduser("~/demucsvenv/bin/python"))
    os.makedirs(out_dir, exist_ok=True)
    work = _tf.mkdtemp()
    try:
        _sp.run([py, "-m", "demucs", "-d", "cpu", "--mp3", "-o", work, audio_path],
                check=True, capture_output=True)
        base = _glob.glob(os.path.join(work, "htdemucs", "*"))
        if not base:
            raise RuntimeError("demucs produced no output")
        base = base[0]
        paths = {}
        for name in ("vocals", "drums", "bass", "other"):
            src = os.path.join(base, f"{name}.mp3")
            if os.path.exists(src):
                dst = os.path.join(out_dir, f"{sid}_{name}.mp3")
                _shutil.move(src, dst)
                paths[name] = dst
        ins = [paths[n] for n in ("drums", "bass", "other") if n in paths]
        if len(ins) >= 2:
            inst = os.path.join(out_dir, f"{sid}_instrumental.mp3")
            cmd = ["ffmpeg", "-y"]
            for p in ins:
                cmd += ["-i", p]
            fc = "".join(f"[{i}:a]" for i in range(len(ins)))
            fc += f"amix=inputs={len(ins)}:duration=longest:normalize=0"
            cmd += ["-filter_complex", fc, "-b:a", "192k", inst]
            _sp.run(cmd, check=True, capture_output=True)
            paths["instrumental"] = inst
        return paths
    finally:
        _shutil.rmtree(work, ignore_errors=True)


def acestep_sfx(prompt: str, duration: float) -> bytes:
    """Generate a sound effect from a text prompt (AudioLDM2 via the :8003 svc)."""
    req = urllib.request.Request(
        ACESTEP_URL + "/sfx",
        data=json.dumps({"prompt": prompt, "duration": duration}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def wav_to_mp3(wav_bytes: bytes) -> bytes:
    bp = tempfile.mktemp(suffix=".wav")
    op = tempfile.mktemp(suffix=".mp3")
    open(bp, "wb").write(wav_bytes)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", bp, "-ac", "2", "-ar", "44100", "-b:a", "192k", op],
            capture_output=True,
        )
        if proc.returncode != 0 or not os.path.exists(op):
            raise RuntimeError("ffmpeg mp3 convert failed")
        return open(op, "rb").read()
    finally:
        for p in (bp, op):
            if os.path.exists(p):
                os.unlink(p)

# Map the classifier's labels onto the product's emotion vocabulary.
_LABEL_MAP = {
    "joy": "happy",
    "happiness": "happy",
    "sadness": "sad",
    "anger": "angry",
    "fear": "fear",
    "surprise": "motivational",
    "love": "romantic",
    "disgust": "angry",
    "neutral": "neutral",
}
SONG_EMOTIONS = [
    "happy", "sad", "romantic", "motivational", "angry", "fear", "nostalgic",
]

_emo_pipe = None
_emo_failed = False


# --------------------------------------------------------------------------- #
# 0. File text extraction (TXT / PDF / DOCX)
# --------------------------------------------------------------------------- #
def extract_text(data: bytes, kind: str) -> str:
    """Extract plain text from an uploaded TXT / PDF / DOCX file."""
    import io

    kind = (kind or "txt").lower()
    if kind == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((pg.extract_text() or "") for pg in reader.pages)
    if kind in ("docx", "doc"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    return data.decode("utf-8", "ignore")


# --------------------------------------------------------------------------- #
# 1. Emotion detection
# --------------------------------------------------------------------------- #
def _lexicon_emotion(text: str) -> dict:
    """Zero-dependency fallback: keyword scoring."""
    t = text.lower()
    kw = {
        "happy": ["happy", "joy", "smile", "celebrate", "fun", "bright", "love life", "dance"],
        "sad": ["sad", "cry", "tears", "alone", "lonely", "lost", "pain", "broken", "miss"],
        "romantic": ["love", "heart", "kiss", "forever", "beautiful", "embrace", "dear"],
        "motivational": ["rise", "dream", "win", "strong", "never give up", "fight", "believe", "goal"],
        "angry": ["angry", "rage", "hate", "fury", "burn", "war", "fight"],
        "fear": ["fear", "afraid", "dark", "scared", "terror", "shadow", "haunt"],
        "nostalgic": ["remember", "memory", "childhood", "old days", "past", "yesterday", "used to"],
    }
    scores = {e: 0.0 for e in SONG_EMOTIONS}
    for emo, words in kw.items():
        for w in words:
            scores[emo] += t.count(w)
    total = sum(scores.values())
    if total == 0:
        scores["happy"] = 1.0
        total = 1.0
    return {e: round(100 * v / total, 1) for e, v in scores.items()}


def analyze_emotion(text: str) -> dict:
    """Return {scores:{emotion:pct}, dominant:str}. Uses an HF model when
    available, else a keyword lexicon. Never raises."""
    global _emo_pipe, _emo_failed
    scores: dict | None = None
    if not _emo_failed:
        try:
            if _emo_pipe is None:
                from transformers import pipeline

                _emo_pipe = pipeline(
                    "text-classification",
                    model="j-hartmann/emotion-english-distilroberta-base",
                    top_k=None,
                    device=-1,  # CPU — keep the GPU for music/vocals
                )
            raw = _emo_pipe(text[:1500])
            rows = raw[0] if isinstance(raw[0], list) else raw
            agg = {e: 0.0 for e in SONG_EMOTIONS}
            for r in rows:
                mapped = _LABEL_MAP.get(r["label"].lower())
                if mapped in agg:
                    agg[mapped] += float(r["score"])
            tot = sum(agg.values())
            if tot > 0:
                scores = {e: round(100 * v / tot, 1) for e, v in agg.items()}
        except Exception as e:
            print(f"[song] emotion model unavailable, using lexicon: {e!r}")
            _emo_failed = True
    if scores is None:
        scores = _lexicon_emotion(text)
    dominant = max(scores, key=lambda k: scores[k])
    return {"scores": scores, "dominant": dominant}


# --------------------------------------------------------------------------- #
# 2. Lyrics structuring
# --------------------------------------------------------------------------- #
def build_lyrics(script: str, title: str | None = None) -> str:
    """Turn a script into a simple song structure (verse / chorus / bridge).
    Deterministic 'basic generation' — no external LLM."""
    # Split into clean sentence-ish lines.
    raw = re.split(r"(?<=[.!?])\s+|\n+", script.strip())
    lines = [re.sub(r"\s+", " ", ln).strip(" .,;:-") for ln in raw if ln.strip()]
    lines = [ln for ln in lines if len(ln) > 2]
    if not lines:
        lines = [script.strip()[:80] or "la la la"]

    # Chorus: the shortest punchy line (memorable hook), repeated.
    hook = min(lines, key=len) if lines else "sing it out loud"
    chorus = f"{hook}\n{hook}, oh oh\n{hook}, tonight"

    def verse(chunk: list[str]) -> str:
        return "\n".join(chunk[:4]) if chunk else hook

    v1 = verse(lines[0:4])
    v2 = verse(lines[4:8] or lines[0:4])
    bridge = verse(lines[8:11] or lines[-3:])

    parts = []
    if title:
        parts.append(f"({title})")
    parts += [
        "[Verse 1]", v1,
        "[Chorus]", chorus,
        "[Verse 2]", v2,
        "[Chorus]", chorus,
        "[Bridge]", bridge,
        "[Outro]", hook,
    ]
    return "\n".join(parts)


def lyrics_to_speakable(lyrics: str) -> str:
    """Strip section tags so the TTS reads only the words."""
    out = [ln for ln in lyrics.splitlines() if not re.match(r"^\s*[\[(]", ln)]
    return ". ".join(x.strip() for x in out if x.strip())


# --------------------------------------------------------------------------- #
# 3. Beat (MusicGen service)
# --------------------------------------------------------------------------- #
def request_beat(genre: str, emotion: str, duration: float, tempo: int | None = None) -> bytes:
    body = json.dumps(
        {"genre": genre, "emotion": emotion, "duration": duration, "tempo": tempo}
    ).encode()
    req = urllib.request.Request(
        MUSICGEN_URL + "/music",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


# --------------------------------------------------------------------------- #
# 4. Mix (ffmpeg): ducked beat under the vocals -> MP3
# --------------------------------------------------------------------------- #
def _wav_duration(b: bytes) -> float:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        p = tf.name
        tf.write(b)
    try:
        with wave.open(p, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0
    finally:
        if os.path.exists(p):
            os.unlink(p)


def mix_to_mp3(
    beat_wav: bytes,
    vocals_wav: bytes,
    intro_sec: float = 2.0,
    beat_gain: float = 0.45,
    vocal_gain: float = 1.6,
) -> bytes:
    """Overlay vocals (delayed by intro_sec) on top of a ducked beat -> MP3."""
    bp = tempfile.mktemp(suffix=".wav")
    vp = tempfile.mktemp(suffix=".wav")
    op = tempfile.mktemp(suffix=".mp3")
    open(bp, "wb").write(beat_wav)
    open(vp, "wb").write(vocals_wav)
    delay_ms = int(intro_sec * 1000)
    fc = (
        f"[0:a]volume={beat_gain}[b];"
        f"[1:a]adelay={delay_ms}|{delay_ms},volume={vocal_gain}[v];"
        f"[b][v]amix=inputs=2:duration=longest:dropout_transition=0,"
        f"dynaudnorm=f=200[a]"
    )
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", bp, "-i", vp, "-filter_complex", fc,
             "-map", "[a]", "-ac", "2", "-ar", "44100", "-b:a", "192k", op],
            capture_output=True,
        )
        if proc.returncode != 0 or not os.path.exists(op):
            raise RuntimeError(
                "ffmpeg mix failed: " + proc.stderr.decode("utf-8", "ignore")[-300:]
            )
        return open(op, "rb").read()
    finally:
        for p in (bp, vp, op):
            if os.path.exists(p):
                os.unlink(p)
