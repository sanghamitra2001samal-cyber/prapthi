#!/usr/bin/env python3
"""Kokoro on the GPU, for live speech.

The app box renders Kokoro on its CPU at about 2x real time, which is fine for
a paragraph but puts 0.6-1 s in front of the first word of a live reply. On
the A10G a short phrase takes ~140 ms (MEASURED 29 Oct 2026: fresh short
phrases, median 139 ms English / 144 ms Hindi; 214/220 ms while svara was
rendering on the same card).

Contract (engine.KokoroEngine calls it, and falls back to its own CPU copy
whenever this does not answer):
    POST /tts  {"text", "voice", "lang", "speed"} -> audio/wav, 24 kHz mono PCM16
    GET  /health -> {"status", "loaded", "device"}

Same model files as the app box (md5-checked), so both paths sound the same.

Two things that cost real time to find:
  * onnxruntime-gpu loads cuDNN's sub-libraries by name at run time. Without
    every site-packages/nvidia/*/lib on LD_LIBRARY_PATH it quietly falls back
    to the CPU — and this box's 4 vCPUs are slower than the app box. The
    loader reads that variable only at process start, so main() sets it and
    re-executes once; and a session that is not on CUDA refuses to start.
  * Every new input length makes cuDNN build a plan. With the default
    HEURISTIC search that is ~240 ms per fresh phrase; DEFAULT is ~160 ms.
    Warming up does not help: live text never repeats a length.
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

HOST = os.environ.get("KOKORO_HOST", "127.0.0.1")
PORT = int(os.environ.get("KOKORO_PORT", "8005"))
MODELS = os.environ.get("KOKORO_MODELS", "/home/ubuntu/kokoro_models")
MAX_CHARS = 2000

_k = None
_lock = threading.Lock()       # one render at a time keeps latency predictable


def log(msg: str) -> None:
    print(f"[kokoro] {msg}", flush=True)


def load() -> None:
    global _k
    import onnxruntime as ort
    from kokoro_onnx import Kokoro

    ort.preload_dlls()
    sess = ort.InferenceSession(
        os.path.join(MODELS, "kokoro-v1.0.onnx"), ort.SessionOptions(),
        providers=[("CUDAExecutionProvider", {
            "cudnn_conv_algo_search": "DEFAULT",
            "arena_extend_strategy": "kSameAsRequested",
            "gpu_mem_limit": 2 * 1024 ** 3,
        })])
    # Never retry on the CPU: a slow answer here is worse than none, because
    # no answer sends the app box to its own (faster) CPU copy.
    sess.disable_fallback()
    k = Kokoro.from_session(sess, os.path.join(MODELS, "voices-v1.0.bin"))
    for line in ("Warming up.", "नमस्ते, शुरू करते हैं।"):
        k.create(line, voice="af_heart", lang="en-us" if line.isascii() else "hi")
    if sess.get_providers()[0] != "CUDAExecutionProvider":
        log(f"not on the GPU ({sess.get_providers()}); refusing to serve")
        sys.exit(1)
    _k = k
    log("loaded on CUDA")


def to_wav(samples: np.ndarray, sr: int) -> bytes:
    pcm = np.clip(np.asarray(samples) * 32768.0, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "kokoro"

    def log_message(self, *a):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _error(self, code: int, msg: str) -> None:
        self._send(code, json.dumps({"error": msg}).encode(), "application/json")

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", ""):
            body = {"status": "ok", "loaded": _k is not None, "device": "cuda"}
            return self._send(200, json.dumps(body).encode(), "application/json")
        return self._error(404, "not found")

    def do_POST(self):
        if self.path.rstrip("/") != "/tts":
            return self._error(404, "not found")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            text = str(req["text"])
            voice = str(req["voice"])
            lang = str(req.get("lang") or "en-us")
            speed = min(2.0, max(0.5, float(req.get("speed", 1.0))))
        except (KeyError, TypeError, ValueError):
            return self._error(400, "text and voice are required")
        if not text.strip() or len(text) > MAX_CHARS:
            return self._error(400, f"text must be 1-{MAX_CHARS} characters")
        if _k is None:
            return self._error(503, "warming up")
        if voice not in _k.get_voices():
            return self._error(400, "unknown voice")
        try:
            with _lock:
                samples, sr = _k.create(text, voice=voice, speed=speed, lang=lang)
        except Exception as e:
            log(f"render failed: {e!r}")
            return self._error(500, "render failed")
        return self._send(200, to_wav(samples, sr), "audio/wav")


def _nvidia_libs() -> None:
    """Put the pip-installed CUDA libraries on the loader path (see above)."""
    import glob
    import site
    libs = [d for sp in site.getsitepackages()
            for d in sorted(glob.glob(os.path.join(sp, "nvidia", "*", "lib")))]
    have = os.environ.get("LD_LIBRARY_PATH", "")
    if libs and not all(d in have.split(":") for d in libs):
        os.environ["LD_LIBRARY_PATH"] = ":".join(libs + ([have] if have else []))
        os.execv(sys.executable, [sys.executable] + sys.argv)


def main() -> None:
    _nvidia_libs()
    load()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    log(f"listening on {HOST}:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
