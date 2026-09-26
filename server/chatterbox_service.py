"""Isolated Chatterbox TTS microservice (Resemble AI, MIT).

Runs in its OWN virtualenv (~/cbx) with its own torch, so it can't disturb the
main app's torch 2.2.2 stack (Kokoro/Piper/Parler/MMS). The main app talks to it
over localhost HTTP via engine.ChatterboxEngine.

Endpoints:
  GET  /health -> {status, device, loaded}
  POST /tts    -> {text, emotion} => audio/wav bytes

Emotion is mapped to Chatterbox's `exaggeration` (expressiveness) and
`cfg_weight` (pacing/deliberateness) knobs.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
import torchaudio as ta
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_LOCK = threading.Lock()  # one GPU — serialize generation
_MODEL = None
_LOADED = threading.Event()

# emotion -> (exaggeration, cfg_weight). Higher exaggeration = more expressive;
# lower cfg_weight = faster/livelier, higher = slower/more deliberate.
_EMO = {
    "neutral": (0.5, 0.5),
    "happy": (0.85, 0.35),   # animated + lively
    "excited": (1.1, 0.3),   # high energy
    "calm": (0.35, 0.65),    # soft + relaxed
    "sad": (0.35, 0.8),      # flat, slow/deliberate
    "serious": (0.5, 0.65),  # measured, deliberate
    "angry": (1.15, 0.35),   # intense, forceful
}


def _get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = ChatterboxMultilingualTTS.from_pretrained(device=DEVICE)
        _LOADED.set()
    return _MODEL


def _warm():
    try:
        _get_model()
        print(f"[chatterbox] model loaded on {DEVICE}", flush=True)
    except Exception as e:  # pragma: no cover
        print(f"[chatterbox] warm load failed: {e!r}", flush=True)


def _synth(
    text: str,
    emotion: str,
    language_id: str = "en",
    audio_prompt_path: str | None = None,
    exaggeration: float | None = None,
    cfg: float | None = None,
) -> bytes:
    # The backend sends each feeling's own values (emotion.py); the
    # table here is only the fallback for older callers.
    d_ex, d_cfg = _EMO.get(emotion, _EMO["neutral"])
    exaggeration = d_ex if exaggeration is None else exaggeration
    cfg = d_cfg if cfg is None else cfg
    gen_kwargs = dict(
        language_id=language_id, exaggeration=exaggeration, cfg_weight=cfg
    )
    # Zero-shot voice cloning: condition on a reference sample if provided.
    if audio_prompt_path and os.path.exists(audio_prompt_path):
        gen_kwargs["audio_prompt_path"] = audio_prompt_path
    with _LOCK:
        m = _get_model()
        wav = m.generate(text, **gen_kwargs)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            path = tf.name
        try:
            ta.save(path, wav.detach().cpu(), m.sr)
            with open(path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(path):
                os.unlink(path)


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
        if self.path != "/tts":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            text = (body.get("text") or "").strip()
            emotion = (body.get("emotion") or "neutral").lower()
            language_id = (body.get("language_id") or "en").lower()
            audio_prompt_path = body.get("audio_prompt_path") or None
            if not text:
                return self._json(400, {"error": "text required"})
            ex = body.get("exaggeration")
            cw = body.get("cfg_weight")
            audio = _synth(
                text, emotion, language_id, audio_prompt_path,
                exaggeration=None if ex is None else float(ex),
                cfg=None if cw is None else float(cw),
            )
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
    port = int(os.environ.get("CBX_PORT", "8001"))
    # Serve immediately; warm the model in the background so /health answers fast.
    threading.Thread(target=_warm, daemon=True).start()
    host = os.environ.get("CBX_HOST", "127.0.0.1")
    print(f"[chatterbox] serving on {host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
