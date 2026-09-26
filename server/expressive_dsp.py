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


def shape(path: str, emotion: str, intensity: float = 1.0, lang: str = "") -> bool:
    """Reshape the WAV at `path` in place. Returns False when nothing applies
    or Praat is unavailable/fails (the caller keeps the original audio)."""
    prof = profile(emotion, intensity, lang)
    if not prof:
        return False
    shift, rng, tempo, gain = prof
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
