#!/usr/bin/env python3
"""Indic Parler-TTS on the GPU, for the website's 93 Parler voices.

On the website server's CPU a Parler sentence takes 30-70 s and holds the lock
that the MMS and Piper voices share, so one customer on a Parler voice made
everyone else wait (measured 7 Nov 2026: MMS 83 s instead of 2 s). Those
voices were hidden for it. Here the same model runs in half precision on the
GPU and the website server calls it, keeping its own CPU copy as the fallback
(as it does for IndicF5).

    POST /tts     {"text": str, "description": str}  -> audio/wav (16-bit mono)
    GET  /health  {"status", "loaded", "device"}

The website server builds the description (speaker, pace, emotion) and does
all post-processing, so a take sounds the same whichever side made it.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import wave
from wsgiref.simple_server import WSGIRequestHandler, make_server

import numpy as np

HOST = os.environ.get("PARLER_HOST", "0.0.0.0")
PORT = int(os.environ.get("PARLER_PORT", "8007"))
MODEL_ID = "ai4bharat/indic-parler-tts"
CACHE = os.environ.get("PARLER_CACHE", "/home/ubuntu/parler_models")
MAX_TEXT = int(os.environ.get("PARLER_MAX_TEXT", "1200"))

_lock = threading.Lock()          # the model is not re-entrant
_state = {"model": None, "tok": None, "desc_tok": None, "device": None, "error": None, "sr": 44100}


def _load() -> None:
    try:
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        dev = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if dev == "cuda" else torch.float32
        # sdpa is refused for the T5 description encoder in transformers
        # 4.46 (tried 8 Nov 2026), so the library default stays.
        attn = os.environ.get("PARLER_ATTN", "eager")
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            MODEL_ID, cache_dir=CACHE, torch_dtype=dtype, attn_implementation=attn).to(dev).eval()
        tok = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=CACHE)
        enc = getattr(model.config, "text_encoder", None)
        desc_tok = AutoTokenizer.from_pretrained(getattr(enc, "_name_or_path", MODEL_ID), cache_dir=CACHE)
        _state.update(model=model, tok=tok, desc_tok=desc_tok, device=dev,
                      sr=int(model.config.sampling_rate))
        print(f"[parler] loaded on {dev} ({dtype}, {attn} attention)", flush=True)
    except Exception as e:  # keep serving /health so the cause is visible
        _state["error"] = repr(e)
        print(f"[parler] load failed: {e!r}", flush=True)


def _synth(text: str, description: str) -> bytes:
    import torch

    m, dev = _state["model"], _state["device"]
    with _lock:
        desc = _state["desc_tok"](description, return_tensors="pt").to(dev)
        prompt = _state["tok"](text, return_tensors="pt").to(dev)
        with torch.inference_mode():
            gen = m.generate(input_ids=desc.input_ids, attention_mask=desc.attention_mask,
                             prompt_input_ids=prompt.input_ids,
                             prompt_attention_mask=prompt.attention_mask)
        samples = gen.float().cpu().numpy().squeeze()
    pcm = np.clip(samples * 32768.0, -32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(_state["sr"])
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def app(environ, start_response):
    path, method = environ.get("PATH_INFO", ""), environ.get("REQUEST_METHOD", "GET")

    def reply(code: str, body: bytes, ctype: str = "application/json"):
        start_response(code, [("Content-Type", ctype), ("Content-Length", str(len(body)))])
        return [body]

    if path == "/health":
        return reply("200 OK", json.dumps({
            "status": "ok", "loaded": _state["model"] is not None,
            "device": _state["device"], "error": _state["error"]}).encode())
    if path != "/tts" or method != "POST":
        return reply("404 Not Found", b'{"error": "not found"}')
    if _state["model"] is None:
        return reply("503 Service Unavailable", b'{"error": "model not loaded"}')
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
        body = json.loads(environ["wsgi.input"].read(n) or b"{}")
        text, description = str(body.get("text", "")).strip(), str(body.get("description", "")).strip()
    except Exception:
        return reply("400 Bad Request", b'{"error": "invalid JSON"}')
    if not text or not description or len(text) > MAX_TEXT:
        return reply("400 Bad Request", b'{"error": "text and description required"}')
    t0 = time.time()
    try:
        wav = _synth(text, description)
    except Exception as e:
        print(f"[parler] synth failed: {e!r}", flush=True)
        return reply("500 Internal Server Error", json.dumps({"error": "synthesis failed"}).encode())
    print(f"[parler] {len(text)} chars in {time.time() - t0:.1f}s", flush=True)
    return reply("200 OK", wav, "audio/wav")


class H(WSGIRequestHandler):
    def log_message(self, *a):          # quiet; we log our own lines
        pass


if __name__ == "__main__":
    threading.Thread(target=_load, daemon=True).start()
    print(f"[parler] listening on {HOST}:{PORT}", flush=True)
    make_server(HOST, PORT, app, handler_class=H).serve_forever()
