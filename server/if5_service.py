"""IndicF5 microservice (AI4Bharat IndicF5 — near-human Indic TTS + cloning).

Runs in its own venv (~/if5, torch 2.6 + transformers 4.46) so its deps don't
touch the main app or the ACE-Step service. IndicF5 is a zero-shot model: every
generation takes a reference clip + its transcript and speaks the new text in
that voice, across 11 Indian languages.

Endpoints:
  GET  /health -> {status, loaded}
  POST /tts    -> {text, ref_audio_path, ref_text} => audio/wav (24kHz)
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import numpy as np
import soundfile as sf
import torch

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_MODEL = None
_LOCK = threading.Lock()
_LOADED = threading.Event()


def _get_model():
    global _MODEL
    if _MODEL is None:
        from transformers import AutoModel
        m = AutoModel.from_pretrained(
            "ai4bharat/IndicF5", trust_remote_code=True, low_cpu_mem_usage=False)
        _MODEL = m.to(DEVICE)
        _LOADED.set()
    return _MODEL


def _tts(text: str, ref_audio_path: str, ref_text: str) -> bytes:
    with _LOCK:
        m = _get_model()
        audio = m(text, ref_audio_path=ref_audio_path, ref_text=ref_text)
        a = np.asarray(audio, dtype=np.float32)
        if np.abs(a).max() > 1.5:      # some builds return int16-scaled floats
            a = a / 32768.0
        out = tempfile.mktemp(suffix=".wav")
        try:
            sf.write(out, a, 24000)
            with open(out, "rb") as f:
                data = f.read()
        finally:
            if os.path.exists(out):
                os.unlink(out)
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        return data


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok", "device": DEVICE, "loaded": _LOADED.is_set()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path != "/tts":
                return self._json(404, {"error": "not found"})
            audio = _tts(body["text"], body["ref_audio_path"], body.get("ref_text", ""))
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        except Exception as e:  # pragma: no cover
            self._json(500, {"error": repr(e)[:300]})

    def log_message(self, *a):
        pass


def _warm():
    try:
        with _LOCK:
            _get_model()
        print(f"[if5] model loaded on {DEVICE}", flush=True)
    except Exception as e:
        print(f"[if5] warm failed: {e!r}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("IF5_PORT", "8004"))
    threading.Thread(target=_warm, daemon=True).start()
    print(f"[if5] serving on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
