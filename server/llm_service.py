"""LLM microservice (Qwen2.5-7B-Instruct via llama.cpp) — the agent's brain.

Self-hosted, multilingual (strong Hindi + English). Runs in its own venv
(~/llm) so its deps don't touch the other services.

Endpoints:
  GET  /health -> {status, loaded}
  POST /chat   -> {messages:[{role,content}], max_tokens?, temperature?} => {reply}
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = os.environ.get(
    "LLM_MODEL", "/home/ubuntu/llm_models/Qwen2.5-7B-Instruct-Q4_K_M.gguf")
_LLM = None
_LOCK = threading.Lock()
_LOADED = threading.Event()


def _get():
    global _LLM
    if _LLM is None:
        from llama_cpp import Llama
        _LLM = Llama(model_path=MODEL, n_gpu_layers=-1, n_ctx=4096,
                     n_threads=4, verbose=False)
        _LOADED.set()
    return _LLM


def _chat(messages: list, max_tokens: int = 256, temperature: float = 0.7) -> str:
    with _LOCK:
        llm = _get()
        out = llm.create_chat_completion(
            messages=messages, max_tokens=max_tokens, temperature=temperature)
        return out["choices"][0]["message"]["content"].strip()


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
            self._json(200, {"status": "ok", "loaded": _LOADED.is_set()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path != "/chat":
                return self._json(404, {"error": "not found"})
            reply = _chat(
                body.get("messages", []),
                int(body.get("max_tokens", 256)),
                float(body.get("temperature", 0.7)),
            )
            self._json(200, {"reply": reply})
        except Exception as e:  # pragma: no cover
            self._json(500, {"error": repr(e)[:300]})

    def log_message(self, *a):
        pass


def _warm():
    try:
        with _LOCK:
            _get()
        print("[llm] model loaded", flush=True)
    except Exception as e:
        print(f"[llm] warm failed: {e!r}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("LLM_PORT", "8005"))
    threading.Thread(target=_warm, daemon=True).start()
    print(f"[llm] serving on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
