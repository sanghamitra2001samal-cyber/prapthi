"""Isolated MusicGen microservice (Meta Audiocraft, MIT — API-free music).

Runs in its OWN virtualenv (~/mg) with torch 2.1, separate from the main app and
the Chatterbox service, so its deps can't disturb anything. The main app talks to
it over localhost HTTP to generate instrumental backing tracks for EmotionSong.

Endpoints:
  GET  /health -> {status, device, loaded}
  POST /music  -> {genre, emotion, tempo, duration} => audio/wav (32 kHz mono-ish)

Model: facebook/musicgen-small (fits the T4 alongside the TTS services).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from audiocraft.data.audio import audio_write
from audiocraft.models import MusicGen

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL_ID = os.environ.get("MUSICGEN_MODEL", "facebook/musicgen-small")
_LOCK = threading.Lock()  # one GPU — serialize generation
_MODEL = None
_LOADED = threading.Event()

# Genre -> descriptive instrumentation prompt fragment.
_GENRE = {
    "pop": "modern pop, catchy, polished, radio-ready, drums and synths",
    "bollywood": "Bollywood film music, Indian instruments, dholak, strings, festive",
    "lofi": "lo-fi hip hop, mellow, warm vinyl, soft piano, chill beat",
    "lo-fi": "lo-fi hip hop, mellow, warm vinyl, soft piano, chill beat",
    "hiphop": "hip hop beat, boom-bap drums, deep bass, head-nodding groove",
    "hip-hop": "hip hop beat, boom-bap drums, deep bass, head-nodding groove",
    "rock": "energetic rock, electric guitars, live drums, driving",
    "edm": "EDM, four-on-the-floor, synth leads, festival energy, build-ups",
    "classical": "Indian classical, sitar, tabla, harmonium, raga mood",
    "rnb": "smooth R&B, silky chords, laid-back groove, soulful",
}

# Emotion -> mood words layered into the prompt.
_EMO_MOOD = {
    "neutral": "balanced, pleasant",
    "happy": "bright, joyful, upbeat, sunny",
    "sad": "melancholic, slow, emotional, minor key",
    "romantic": "warm, tender, romantic, intimate",
    "motivational": "uplifting, triumphant, inspiring, powerful",
    "angry": "intense, aggressive, hard-hitting, dark",
    "fear": "tense, suspenseful, eerie, cinematic",
    "nostalgic": "wistful, nostalgic, warm, reflective",
    "inspirational": "hopeful, soaring, cinematic, uplifting",
    "excited": "high-energy, fast, exciting",
    "calm": "calm, gentle, peaceful, ambient",
}


def _prompt(genre: str, emotion: str, tempo: int | None) -> str:
    g = _GENRE.get((genre or "pop").lower(), _GENRE["pop"])
    mood = _EMO_MOOD.get((emotion or "neutral").lower(), _EMO_MOOD["neutral"])
    parts = [g, mood, "instrumental, no vocals, high quality"]
    if tempo:
        parts.append(f"around {int(tempo)} bpm")
    return ", ".join(parts)


def _get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = MusicGen.get_pretrained(MODEL_ID, device=DEVICE)
        _LOADED.set()
    return _MODEL


def _warm():
    try:
        _get_model()
        print(f"[musicgen] model loaded on {DEVICE}", flush=True)
    except Exception as e:  # pragma: no cover
        print(f"[musicgen] warm load failed: {e!r}", flush=True)


def _generate(genre: str, emotion: str, tempo: int | None, duration: float) -> bytes:
    duration = max(5.0, min(float(duration or 30), 180.0))  # cap 3 min
    prompt = _prompt(genre, emotion, tempo)
    with _LOCK:
        m = _get_model()
        m.set_generation_params(duration=duration, use_sampling=True, top_k=250)
        wav = m.generate([prompt])  # (1, channels, samples)
        stem = tempfile.mktemp()
        try:
            # audio_write appends .wav; loudness strategy keeps it clean.
            audio_write(stem, wav[0].cpu(), m.sample_rate, strategy="loudness")
            path = stem + ".wav"
            with open(path, "rb") as f:
                return f.read()
        finally:
            p = stem + ".wav"
            if os.path.exists(p):
                os.unlink(p)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json(
                200,
                {"status": "ok", "device": DEVICE, "loaded": _LOADED.is_set()},
            )
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/music":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            genre = (body.get("genre") or "pop").lower()
            emotion = (body.get("emotion") or "neutral").lower()
            tempo = body.get("tempo")
            duration = body.get("duration") or 30
            audio = _generate(genre, emotion, tempo, duration)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        except Exception as e:  # pragma: no cover
            self._json(500, {"error": repr(e)[:200]})

    def log_message(self, *args):  # silence default logging
        pass


if __name__ == "__main__":
    port = int(os.environ.get("MUSICGEN_PORT", "8002"))
    threading.Thread(target=_warm, daemon=True).start()
    print(f"[musicgen] serving on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
