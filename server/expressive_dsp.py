"""Expressive tone shaping for voices whose engine cannot emote.

The old approach (ffmpeg asetrate) moved the WHOLE pitch contour up or down,
which keeps the melody flat and sounds robotic: measured pitch spread barely
changed between emotions (57-71 Hz).  Real feelings change the *range* of
the melody: joy swings wider, sadness and sympathy go flatter and lower.

This reshapes the contour with Praat (PSOLA), per feeling:
    new_f0 = mean * shift * (f0 / mean) ** range
plus tempo and loudness.  Voice timbre is untouched, so the speaker stays
recognisable.  It is still tone, not true emotional acting — engines that can
really emote (svara, Chatterbox) are always preferred when available.
"""
from __future__ import annotations

import os

# feeling -> (mean pitch shift, pitch-range factor, tempo, gain dB)
PROFILES: dict[str, tuple[float, float, float, float]] = {
    "happy":        (1.08, 1.45, 1.04, 1.5),
    "excited":      (1.12, 1.65, 1.08, 2.5),
    "surprise":     (1.10, 1.60, 1.02, 2.0),
    "hopeful":      (1.04, 1.25, 1.00, 0.5),
    "grateful":     (1.03, 1.20, 0.98, 0.0),
    "sad":          (0.93, 0.55, 0.88, -2.5),
    "sympathetic":  (0.96, 0.65, 0.90, -3.0),
    "empathetic":   (0.97, 0.72, 0.93, -2.0),
    "apologetic":   (0.96, 0.70, 0.93, -2.0),
    "reassuring":   (0.97, 0.80, 0.94, -1.0),
    "calm":         (0.97, 0.75, 0.94, -1.5),
    "romantic":     (0.97, 0.85, 0.92, -2.5),
    "whisper":      (1.00, 0.60, 0.95, -9.0),
    "angry":        (1.03, 1.35, 1.03, 3.5),
    "disgust":      (0.95, 1.20, 0.96, 1.0),
    "fear":         (1.07, 1.30, 1.06, -1.5),
    "urgent":       (1.05, 1.25, 1.10, 2.5),
    "command":      (0.97, 1.15, 0.98, 3.0),
    "confident":    (0.99, 1.15, 1.00, 1.5),
    "serious":      (0.96, 0.85, 0.97, 0.5),
    "news":         (1.00, 1.05, 1.03, 1.0),
    "narration":    (1.00, 1.20, 0.96, 0.0),
    "conversation": (1.01, 1.15, 1.02, 0.0),
    "sarcastic":    (1.02, 1.40, 0.95, 0.0),
}


# In tonal languages pitch movement IS the word: squashing the contour turned
# Vietnamese "tiếc" (sorry) into "tiếp" (continue) in testing.  Only the level,
# tempo and loudness may change there.
TONAL = {"vi", "zh", "yue", "cmn", "th", "lo", "my", "km", "yo", "ig", "ha"}


def profile(emotion: str, intensity: float = 1.0, lang: str = ""):
    p = PROFILES.get(emotion)
    if not p:
        return None
    k = max(0.0, min(2.0, float(intensity)))
    shift, rng, tempo, gain = p
    rng = 1 + (rng - 1) * k
    if lang.split("-")[0].lower() in TONAL:
        rng = 1.0
    return (1 + (shift - 1) * k, rng, 1 + (tempo - 1) * k, gain * k)


# svara acts a feeling itself, but every one of its tags pushes the voice UP:
# measured Sep 2026 against no tag, <happy> +102 Hz, <anger> +77 Hz, <sad>
# +44 Hz. So sad never sounded sad and angry sounded like happy, and the flat
# speed/volume nudge on top changed nothing a listener could hear (the owner,
# 9 Nov 2026: "too weak", "sad is not sad", "angry sounds like happy", "fake").
# On top of the tag, each feeling now also gets the shape real speech has:
#   happy: higher, wider melody, a little brighter
#   sad:   lower, flatter, slower, softer and duller (high frequencies down)
#   angry: NOT higher than normal, wider melody, faster, louder, pressed and
#          harsh (presence boost + compression) - the cue that sets it apart
# feeling -> (pitch shift, range, tempo, level dB vs neutral, ffmpeg tone filter with {g}, tone dB)
# "level" is set against the measured speaking level of neutral svara speech after
# the shared finisher (-16.7 dBFS median over 14 clips, 9 Nov 2026). It cannot be a
# plain gain: the finisher normalises each clip's PEAK, so angry speech, all sharp
# peaks, came out 3.6 dB QUIETER than neutral before any shaping, and a compressor's
# make-up could not win that back. Peaks are caught by a limiter instead.
SVARA_LEVEL_DB = -16.7
SVARA_PROFILES: dict[str, tuple[float, float, float, float, str, float]] = {
    "happy": (1.05, 1.30, 1.04, 1.0, "highshelf=f=5000:g={g}", 3.0),
    "sad": (0.92, 0.60, 0.93, -3.0, "highshelf=f=2800:g=-{g}", 4.0),
    # the tag lifts anger ~77 Hz; pulling it back down is what keeps it from
    # sounding like joy, and the pressed, compressed 1.8 kHz is the anger.
    # svara's own tags already speed anger up and slow sadness down, so the
    # tempo here is only a nudge (more measured as overacting: +32%, -22%).
    "angry": (0.92, 1.25, 1.03, 4.0,
              "acompressor=threshold=-30dB:ratio=5:attack=2:release=40,equalizer=f=1800:t=q:w=1.0:g={g}", 6.0),
}


def svara_profile(emotion: str, strength: float = 1.0, lang: str = ""):
    p = SVARA_PROFILES.get(emotion)
    if not p:
        return None
    shift, rng, tempo, level, tone, tone_db = p
    k = max(0.0, min(2.0, float(strength)))
    rng = 1 + (rng - 1) * k
    if lang.split("-")[0].lower() in TONAL:
        rng = 1.0
    return (1 + (shift - 1) * k, rng, 1 + (tempo - 1) * k, level * k,
            tone.format(g=f"{tone_db * k:.2f}"))


def _active_db(path: str) -> float | None:
    """Speaking level: mean power of 20 ms frames above -45 dBFS."""
    import numpy as np
    import parselmouth
    snd = parselmouth.Sound(path)
    y = snd.values[0]
    n = max(1, int(0.02 * snd.sampling_frequency))
    fr = y[: len(y) // n * n].reshape(-1, n)
    db = 10 * np.log10(np.maximum(1e-12, (fr ** 2).mean(axis=1)))
    act = db[db > -45]
    return float(10 * np.log10(np.mean(10 ** (act / 10)))) if act.size else None


def shape_svara(path: str, emotion: str, strength: float = 1.0, lang: str = "",
                volume: float = 1.0) -> bool:
    """Shape a svara render in place for `emotion` (see SVARA_PROFILES).
    `volume` is the user's own volume slider, kept on top of the feeling."""
    import math
    import subprocess
    prof = svara_profile(emotion, strength, lang)
    if not prof:
        return False
    shift, rng, tempo, level, tone = prof
    if not _reshape(path, emotion, shift, rng, tempo, 0.0):
        return False
    tmp, tmp2 = path + ".tone.wav", path + ".lvl.wav"
    try:
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-af", tone, tmp],
                           capture_output=True, timeout=60)
        src = tmp if r.returncode == 0 and os.path.exists(tmp) else path
        have = _active_db(src)
        target = SVARA_LEVEL_DB + level + 20 * math.log10(max(0.05, float(volume or 1.0)))
        # up to 24 dB: the anger compressor alone takes ~11 dB off (measured)
        gain = 0.0 if have is None else max(-24.0, min(24.0, target - have))
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af",
                            f"volume={gain:.2f}dB,alimiter=limit=0.97:level=0", tmp2],
                           capture_output=True, timeout=60)
        if r.returncode == 0 and os.path.exists(tmp2):
            os.replace(tmp2, path)
    except Exception as e:  # the reshaped audio is still good without tone/level
        print(f"[expressive_dsp] svara tone {emotion}: {e!r}")
    finally:
        for t in (tmp, tmp2):
            if os.path.exists(t):
                os.unlink(t)
    return True


def shape(path: str, emotion: str, intensity: float = 1.0, lang: str = "") -> bool:
    """Reshape the WAV at `path` in place. Returns False when nothing applies
    or Praat is unavailable/fails (the caller keeps the original audio)."""
    prof = profile(emotion, intensity, lang)
    if not prof:
        return False
    return _reshape(path, emotion, *prof)


def _reshape(path: str, emotion: str, shift: float, rng: float, tempo: float, gain: float) -> bool:
    try:
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        return False
    try:
        snd = parselmouth.Sound(path)
        dur = snd.get_total_duration()
        if dur < 0.3:
            return False
        manip = call(snd, "To Manipulation", 0.01, 60, 600)
        tier = call(manip, "Extract pitch tier")
        n = call(tier, "Get number of points")
        if n >= 3:
            mean = call(tier, "Get mean (points)", 0, 0)
            if mean and mean == mean:  # not NaN
                call(tier, "Formula",
                     f"{mean * shift:.4f} * (self / {mean:.4f}) ^ {rng:.4f}")
                call([tier, manip], "Replace pitch tier")
        if abs(tempo - 1) > 1e-3:
            dt = call("Create DurationTier", "d", 0, dur)
            call(dt, "Add point", 0, 1 / tempo)
            call([manip, dt], "Replace duration tier")
        out = call(manip, "Get resynthesis (overlap-add)")
        if abs(gain) > 1e-3:
            out.values *= 10 ** (gain / 20)
        peak = abs(out.values).max()
        if peak > 0.97:
            out.values *= 0.97 / peak
        tmp = path + ".xp.wav"
        out.save(tmp, "WAV")
        os.replace(tmp, path)
        return True
    except Exception as e:  # never fail a synthesis over tone shaping
        print(f"[expressive_dsp] {emotion}: {e!r}")
        return False
