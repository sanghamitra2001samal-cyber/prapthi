#!/usr/bin/env python3
"""IndicF5 sidecar for Prapthi — near-human Indic TTS + voice cloning.

Serves the contract engine.if5_synth expects:
    POST /tts  {"text", "ref_audio_path", "ref_text"}  -> audio/wav bytes
    GET  /health -> {"status","loaded","device"}

Runs on the GCP box (NOT the GPU): ref_audio_path is a filesystem path to the
user's clone sample, which only exists here.  Same cross-host trap as ACE-Step
/stems and Chatterbox audio_prompt_path.

The model is held resident — loading it per request would cost ~30s each time.
"""
import io
import json
import os
import threading
import wave

import numpy as np

HOST = os.environ.get("IF5_HOST", "127.0.0.1")
PORT = int(os.environ.get("IF5_PORT", "8004"))
REPO = os.environ.get("IF5_REPO", "ai4bharat/IndicF5")
DEVICE = os.environ.get("IF5_DEVICE", "cpu")
SR = int(os.environ.get("IF5_SR", "24000"))

_model = None
_lock = threading.Lock()          # the model is not re-entrant
_load_err: str | None = None


class _IF5:
    """IndicF5 without its transformers wrapper.

    transformers >=4.5x builds remote-code models on the meta device, but the
    IndicF5 wrapper loads real weights inside __init__ -> "Cannot copy out of
    meta tensor". So build the DiT/CFM + vocos directly (same recipe as the
    wrapper) and load the bundled model.safetensors ourselves.
    """

    PREFIX_M = "ema_model._orig_mod."
    PREFIX_V = "vocoder._orig_mod."

    def __init__(self) -> None:
        import sys
        import torch
        from huggingface_hub import hf_hub_download, snapshot_download
        from safetensors.torch import load_file

        # The repo ships the f5_tts code it was trained with. Its own wrapper
        # sys.path.APPENDs it, so a pip-installed f5-tts (1.x: different DiT
        # defaults, same tensor shapes) silently wins and the output is
        # gibberish. Put the bundled copy FIRST.
        snap = snapshot_download(REPO)
        sys.path.insert(0, snap)
        from f5_tts.infer import utils_infer as u
        from f5_tts.model import CFM, DiT
        from f5_tts.model.utils import get_tokenizer

        self.u = u
        self.device = torch.device(DEVICE)
        vocab = hf_hub_download(REPO, "checkpoints/vocab.txt")
        sd = load_file(os.path.join(snap, "model.safetensors"))

        vocab_map, vocab_size = get_tokenizer(vocab, "custom")
        model = CFM(
            transformer=DiT(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512,
                            conv_layers=4, text_num_embeds=vocab_size,
                            mel_dim=u.n_mel_channels),
            mel_spec_kwargs=dict(n_fft=u.n_fft, hop_length=u.hop_length,
                                 win_length=u.win_length,
                                 n_mel_channels=u.n_mel_channels,
                                 target_sample_rate=u.target_sample_rate,
                                 mel_spec_type="vocos"),
            odeint_kwargs=dict(method="euler"),
            vocab_char_map=vocab_map,
        )
        msd = {k[len(self.PREFIX_M):]: v for k, v in sd.items()
               if k.startswith(self.PREFIX_M)}
        missing, unexpected = model.load_state_dict(msd, strict=False)
        # CFM carries no learned tensors besides the transformer; anything
        # missing from the DiT itself means the recipe is wrong.
        bad = [k for k in missing if k.startswith("transformer.")]
        if bad or unexpected:
            raise RuntimeError(f"weight mismatch: missing={bad[:5]} unexpected={unexpected[:5]}")
        self.model = model.eval().to(self.device)

        voc = u.load_vocoder("vocos", is_local=True,
                             local_path=snapshot_download("charactr/vocos-mel-24khz"),
                             device="cpu")
        vsd = {k[len(self.PREFIX_V):]: v for k, v in sd.items()
               if k.startswith(self.PREFIX_V)}
        if vsd:
            voc.load_state_dict(vsd, strict=False)
        self.vocoder = voc.eval().to(self.device)
        # 16, not f5_tts's default 32. Measured on three Hindi sentences
        # through this service: word-error rate identical (31.3% either way)
        # and median pitch within 0.3 Hz, for half the generation time —
        # 74s -> 37.5s per 55 characters on this CPU box. 8 is faster again
        # but shifts pitch ~7 Hz, i.e. the voice itself drifts, so 16 is the
        # floor worth using.
        #
        # entitlements._ENGINE_LIMITS["if5"] derives the character cap from
        # this speed. Put that rate back toward 1.58 if this returns to 32.
        self.nfe = int(os.environ.get("IF5_NFE", "16"))

    def __call__(self, text, ref_audio_path, ref_text):
        import torch
        u = self.u
        ref_audio, ref_text = u.preprocess_ref_audio_text(
            ref_audio_path, ref_text, show_info=lambda *a, **k: None)
        with torch.inference_mode():
            audio, _sr, _ = u.infer_process(
                ref_audio, ref_text, text, self.model, self.vocoder,
                mel_spec_type="vocos", nfe_step=self.nfe, device=self.device,
                show_info=lambda *a, **k: None)
        return audio


def _load() -> None:
    global _model, _load_err
    try:
        import time
        t = time.time()
        _model = _IF5()
        print(f"[if5] loaded {REPO} on {DEVICE} in {time.time()-t:.1f}s", flush=True)
    except Exception as e:                       # keep serving /health
        _load_err = repr(e)
        print(f"[if5] LOAD FAILED: {e!r}", flush=True)


def _to_wav(audio) -> bytes:
    a = np.asarray(audio, dtype=np.float32).squeeze()
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    # IndicF5 returns float in roughly [-1,1]; some builds return int16 range.
    if peak > 1.5:
        a = a / 32768.0
        peak = float(np.max(np.abs(a)))
    if peak > 1.0:
        a = a / peak
    pcm = (a * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def app(environ, start_response):
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "GET")

    if path == "/health":
        body = json.dumps({
            "status": "ok",
            "loaded": _model is not None,
            "device": DEVICE,
            "error": _load_err,
        }).encode()
        start_response("200 OK", [("Content-Type", "application/json"),
                                  ("Content-Length", str(len(body)))])
        return [body]

    if path != "/tts" or method != "POST":
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"not found"]

    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
        req = json.loads(environ["wsgi.input"].read(n) or b"{}")
        text = (req.get("text") or "").strip()
        ref_audio = req.get("ref_audio_path") or ""
        ref_text = (req.get("ref_text") or "").strip()
        if not text:
            raise ValueError("text required")
        if not ref_audio or not os.path.exists(ref_audio):
            raise ValueError(f"ref_audio_path not found: {ref_audio}")
        if _model is None:
            raise RuntimeError(f"model not loaded: {_load_err}")

        with _lock:
            audio = _model(text, ref_audio_path=ref_audio, ref_text=ref_text)
        wav = _to_wav(audio)
    except Exception as e:
        body = json.dumps({"error": repr(e)}).encode()
        print(f"[if5] error: {e!r}", flush=True)
        start_response("500 Internal Server Error",
                       [("Content-Type", "application/json"),
                        ("Content-Length", str(len(body)))])
        return [body]

    start_response("200 OK", [("Content-Type", "audio/wav"),
                              ("Content-Length", str(len(wav)))])
    return [wav]


if __name__ == "__main__":
    from wsgiref.simple_server import make_server, WSGIRequestHandler

    class H(WSGIRequestHandler):
        protocol_version = "HTTP/1.1"

    threading.Thread(target=_load, daemon=True).start()
    print(f"[if5] listening on {HOST}:{PORT}", flush=True)
    make_server(HOST, PORT, app, handler_class=H).serve_forever()
