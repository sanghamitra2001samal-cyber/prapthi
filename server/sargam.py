"""Deterministic notation -> audio engine (API-free, note-level control).

Unlike the ACE-Step song model (which is prompt-conditioned and cannot play an
exact note sequence), this module renders an *exact* melody from notation:

  * Indian Sargam : S R G M P D N  (+ komal r g d n, tivra Ma 'm')
  * Western solfege: do re mi fa sol la ti
  * Letter notes  : C D E F G A B  (with #/b and octave digits)

The notes are universal — the same pitches regardless of language — so the
melody can be rendered in *any* instrument (sitar, bansuri, piano, violin…)
via FluidSynth + a General-MIDI SoundFont. Fully offline, deterministic, and
perfectly in tune.

Pipeline:  notation text -> [(midi_note|rest, beats)] -> MIDI file -> FluidSynth
           render (SoundFont) -> WAV -> MP3.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile

SOUNDFONT = os.environ.get(
    "SARGAM_SOUNDFONT", "/usr/share/sounds/sf2/FluidR3_GM.sf2"
)

# --- tonic / key -> base MIDI (Sa) ----------------------------------------- #
_KEY_MIDI = {
    "c": 60, "c#": 61, "db": 61, "d": 62, "d#": 63, "eb": 63, "e": 64,
    "f": 65, "f#": 66, "gb": 66, "g": 67, "g#": 68, "ab": 68, "a": 69,
    "a#": 70, "bb": 70, "b": 71,
}

# --- Sargam swara -> semitone offset from Sa ------------------------------- #
#   uppercase = shuddha, lowercase r/g/d/n = komal, lowercase m = tivra Ma.
#   Sa (S) and Pa (P) are achala (fixed).
_SARGAM = {
    "S": 0, "r": 1, "R": 2, "g": 3, "G": 4, "M": 5, "m": 6,
    "P": 7, "d": 8, "D": 9, "n": 10, "N": 11,
}

# --- solfege (movable do) -> semitone offset ------------------------------- #
_SOLFEGE = {
    "do": 0, "di": 1, "ra": 1, "re": 2, "ri": 3, "me": 3, "mi": 4,
    "fa": 5, "fi": 6, "se": 6, "sol": 7, "so": 7, "si": 8, "le": 8,
    "la": 9, "li": 10, "te": 10, "ti": 11,
}

# --- letter note -> semitone within octave --------------------------------- #
_LETTER = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

# --- instrument display name -> General MIDI program (0-indexed) ----------- #
GM_PROGRAM = {
    "grand piano": 0, "upright piano": 0, "piano": 0, "electric piano": 4,
    "keyboard": 4, "organ": 19, "harmonium": 20, "accordion": 21, "harp": 46,
    "acoustic guitar": 24, "classical guitar": 24, "nylon guitar": 24,
    "electric guitar": 27, "lead guitar": 29, "rhythm guitar": 27,
    "twelve-string guitar": 25, "ukulele": 24, "mandolin": 25,
    "solo violin": 40, "violin": 40, "violin section": 48, "viola": 41,
    "cello": 42, "double bass": 43, "upright bass": 43, "acoustic bass": 32,
    "electric bass": 33, "synth bass": 38, "string ensemble": 48,
    "concert flute": 73, "flute": 73, "bansuri flute": 73, "bansuri": 73,
    "piccolo": 72, "pan flute": 75, "clarinet": 71, "oboe": 68, "bassoon": 70,
    "saxophone": 65, "sax": 65, "trumpet": 56, "trombone": 57,
    "french horn": 60, "tuba": 58, "brass ensemble": 61,
    "sitar": 104, "sarod": 105, "santoor": 15, "veena": 104, "sarangi": 110,
    "shehnai": 111, "shanai": 111, "tanpura": 104,
    "synth lead": 80, "synth pad": 89, "analog synth": 81, "digital synth": 81,
    "pluck synth": 84, "fx synth": 99, "arpeggiator": 80,
    "choir": 52, "backing vocals": 53, "vocal harmonies": 52, "vocal pads": 54,
    "bells": 14, "chimes": 14, "celesta": 8, "glockenspiel": 9,
    "marimba": 12, "xylophone": 13, "kalimba": 108, "steel drums": 114,
    "oud": 105, "duduk": 68, "bagpipes": 109,
}

MAX_NOTES = 2000


class NotationError(ValueError):
    pass


def _octave_shift(token: str) -> tuple[str, int]:
    """Strip trailing ' (up) and , (down) octave markers; return (core, shift)."""
    shift = 0
    while token and token[-1] in "',":
        shift += 12 if token[-1] == "'" else -12
        token = token[:-1]
    return token, shift


def _split_duration(token: str) -> tuple[str, int]:
    """A token may end with one or more '-' to extend its length (each +1 beat)."""
    beats = 1
    while token.endswith("-"):
        beats += 1
        token = token[:-1]
    return token, beats


def detect_system(text: str) -> str:
    t = text.strip()
    words = re.findall(r"[a-z]+", t.lower())
    if any(w in _SOLFEGE for w in words if len(w) >= 2):
        return "solfege"
    # Letters A,B,C,E,F are western-only; S,P,N are sargam-only. D and G are
    # shared, so we discriminate on the unambiguous ones.
    has_western = any(ch in "CEFABcefab" for ch in t)
    has_sargam = any(ch in "SPNspmn" for ch in t)
    if has_western and not has_sargam:
        return "western"
    return "sargam"


def parse_notation(
    text: str, system: str = "auto", tonic: str = "C"
) -> list[tuple[int | None, int]]:
    """Return a list of (midi_note | None for rest, beats)."""
    if system in ("", "auto"):
        system = detect_system(text)
    base = _KEY_MIDI.get((tonic or "C").strip().lower(), 60)

    # normalise separators: bar lines and newlines -> spaces
    raw = re.sub(r"[|\n\r\t]+", " ", text.strip())
    events: list[tuple[int | None, int]] = []

    if system == "solfege":
        tokens = raw.lower().split()
        for tok in tokens:
            tok, beats = _split_duration(tok)
            tok, shift = _octave_shift(tok)
            if tok in ("_", "-", "rest"):
                events.append((None, beats))
                continue
            if tok in _SOLFEGE:
                events.append((base + _SOLFEGE[tok] + shift, beats))
            elif tok:
                raise NotationError(f"Unknown solfege syllable: {tok!r}")
    elif system == "western":
        for tok in raw.split():
            tok, beats = _split_duration(tok)
            if tok in ("_", "rest"):
                events.append((None, beats))
                continue
            m = re.match(r"^([A-Ga-g])([#b]?)(\d?)$", tok)
            if not m:
                raise NotationError(f"Unknown note: {tok!r}")
            letter, acc, octv = m.groups()
            semi = _LETTER[letter.lower()] + (1 if acc == "#" else -1 if acc == "b" else 0)
            octave = int(octv) if octv else 4
            events.append((12 * (octave + 1) + semi, beats))
    else:  # sargam
        for tok in raw.split():
            tok, beats = _split_duration(tok)
            tok, shift = _octave_shift(tok)
            if tok in ("_", "rest"):
                events.append((None, beats))
                continue
            if tok in _SARGAM:
                events.append((base + _SARGAM[tok] + shift, beats))
            elif tok:
                raise NotationError(
                    f"Unknown swara: {tok!r} (use S r R g G M m P d D n N, "
                    f"octave with ' or , , extend with -, rest with _)"
                )
        if not events:
            raise NotationError("No notes parsed.")

    if len(events) > MAX_NOTES:
        events = events[:MAX_NOTES]
    if not events:
        raise NotationError("No notes parsed.")
    return events


def _build_midi(
    events: list[tuple[int | None, int]], program: int, bpm: int,
    velocity: int = 100,
) -> bytes:
    from midiutil import MIDIFile

    mf = MIDIFile(1, deinterleave=False)
    mf.addTempo(0, 0, max(30, min(bpm, 300)))
    mf.addProgramChange(0, 0, 0, max(0, min(program, 127)))
    t = 0.0
    for note, beats in events:
        dur = float(beats)
        if note is not None and 0 <= note <= 127:
            # slight detache so repeated notes articulate
            mf.addNote(0, 0, int(note), t, max(0.25, dur * 0.95), velocity)
        t += dur
    bio = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
    try:
        mf.writeFile(bio)
        bio.flush()
        bio.close()
        with open(bio.name, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(bio.name):
            os.unlink(bio.name)


def render(
    notation: str, system: str = "auto", tonic: str = "C",
    instrument: str = "grand piano", bpm: int = 90, fmt: str = "mp3",
) -> bytes:
    """Render notation to audio bytes (mp3 by default) in the chosen instrument."""
    events = parse_notation(notation, system, tonic)
    program = GM_PROGRAM.get((instrument or "grand piano").strip().lower(), 0)
    midi = _build_midi(events, program, int(bpm or 90))

    mid_p = tempfile.mktemp(suffix=".mid")
    wav_p = tempfile.mktemp(suffix=".wav")
    out_p = tempfile.mktemp(suffix=f".{ 'mp3' if fmt != 'wav' else 'wav' }")
    try:
        with open(mid_p, "wb") as f:
            f.write(midi)
        if not os.path.exists(SOUNDFONT):
            raise NotationError("SoundFont not found on server.")
        proc = subprocess.run(
            ["fluidsynth", "-ni", "-g", "1.2", "-R", "1", "-F", wav_p,
             "-r", "44100", SOUNDFONT, mid_p],
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0 or not os.path.exists(wav_p):
            raise NotationError(
                "render failed: " + proc.stderr.decode("utf-8", "ignore")[-200:]
            )
        if fmt == "wav":
            with open(wav_p, "rb") as f:
                return f.read()
        # normalise + encode mp3
        enc = subprocess.run(
            ["ffmpeg", "-y", "-i", wav_p, "-af", "dynaudnorm=f=200",
             "-ac", "2", "-ar", "44100", "-b:a", "192k", out_p],
            capture_output=True, timeout=120,
        )
        if enc.returncode != 0 or not os.path.exists(out_p):
            raise NotationError("mp3 encode failed")
        with open(out_p, "rb") as f:
            return f.read()
    finally:
        for p in (mid_p, wav_p, out_p):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def notation_summary(notation: str, system: str = "auto", tonic: str = "C") -> dict:
    """Parse + report note count / beats / detected system (for the UI)."""
    sys_ = detect_system(notation) if system in ("", "auto") else system
    events = parse_notation(notation, sys_, tonic)
    beats = sum(b for _, b in events)
    notes = sum(1 for n, _ in events if n is not None)
    return {"system": sys_, "notes": notes, "beats": beats}
