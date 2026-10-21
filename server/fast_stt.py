"""Fast Hindi speech-to-text for short phone answers.

Whisper always encodes a 30-second window, so even a one-word reply costs ~1.1 s on this CPU.
A CTC wav2vec2 model's cost grows with the audio itself: measured on the VM, a short Hindi
answer takes ~0.1 s and is read at least as accurately ("हाँ" stays हाँ; Whisper small wrote
"है"). Used by /stt/fast for Hindi; other languages go to Whisper.

The model runs in its own worker process. PyTorch (this model) and CTranslate2 (Whisper) each
bring an OpenMP runtime; once both had run inside the server process, Whisper's /transcribe
hung on a lock and never answered. A separate process keeps them apart; handing an answer's
audio to the worker costs about a millisecond.

Model: Vakyansh (EkStep) wav2vec2 trained on ~4,200 h of Hindi, decoded greedily (no LM).
Override with VOXFORGE_FAST_STT_MODEL.
"""

import concurrent.futures as _cf
import multiprocessing as _mp
import os
import re
import threading

import numpy as np

MODEL = os.environ.get("VOXFORGE_FAST_STT_MODEL", "Harveenchadha/vakyansh-wav2vec2-hindi-him-4200")
TIMEOUT_S = float(os.environ.get("VOXFORGE_FAST_STT_TIMEOUT", "20"))

# ---- Worker process: owns PyTorch and the model ----

_proc = None
_model = None


def _load():
    global _proc, _model
    if _model is None:
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        torch.set_num_threads(int(os.environ.get("VOXFORGE_FAST_STT_THREADS", "4")))
        _proc = Wav2Vec2Processor.from_pretrained(MODEL)
        _model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    return _proc, _model


def _worker_transcribe(pcm: bytes, sample_rate: int) -> str:
    """Runs in the worker process: raw mono 16-bit PCM → Hindi text."""
    import torch

    proc, model = _load()
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if sample_rate != 16000 and audio.size:
        # Linear resample to the model's 16 kHz (phone audio is 8 kHz).
        n = int(round(audio.size * 16000 / sample_rate))
        audio = np.interp(np.linspace(0, audio.size - 1, n), np.arange(audio.size), audio).astype(np.float32)
    if audio.size < 400:  # under 25 ms: nothing to read
        return ""
    inputs = proc(audio, sampling_rate=16000, return_tensors="pt")
    with torch.inference_mode():
        logits = model(inputs.input_values).logits
    text = proc.batch_decode(torch.argmax(logits, dim=-1))[0]
    # This vocabulary emits its pad token "<s>" between characters; drop it.
    text = text.replace("<s>", "").replace("</s>", "")
    return re.sub(r"\s+", " ", text).strip()


# ---- Server side: hands audio to the worker ----

_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            # "spawn" starts a clean interpreter: nothing of the server's runtimes is inherited.
            _pool = _cf.ProcessPoolExecutor(max_workers=1, mp_context=_mp.get_context("spawn"))
        return _pool


def _reset_pool():
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def transcribe_pcm(pcm: bytes, sample_rate: int = 16000) -> str:
    """Raw mono 16-bit PCM → Hindi text, computed in the worker process."""
    for attempt in (1, 2):
        try:
            return _get_pool().submit(_worker_transcribe, pcm, sample_rate).result(timeout=TIMEOUT_S)
        except _cf.process.BrokenProcessPool:
            _reset_pool()  # the worker died (e.g. out of memory): start a fresh one once
            if attempt == 2:
                raise
    return ""


def warm() -> None:
    """Start the worker and load the model, so the first caller does not wait for it."""
    transcribe_pcm(np.zeros(1600, dtype=np.int16).tobytes(), 16000)
