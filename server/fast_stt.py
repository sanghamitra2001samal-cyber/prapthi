"""Fast Hindi speech-to-text for short phone answers.

Whisper always encodes a 30-second window, so even a one-word reply costs ~1.1 s on this CPU.
A CTC wav2vec2 model's cost grows with the audio itself: measured on the VM, a short Hindi
answer takes ~0.1 s and is read at least as accurately ("हाँ" stays हाँ; Whisper small wrote
"है"). Used by /stt/fast for Hindi; other languages go to Whisper.

Model: Vakyansh (EkStep) wav2vec2 trained on ~4,200 h of Hindi, decoded greedily (no LM).
Override with VOXFORGE_FAST_STT_MODEL.
"""

import os
import re
import threading

import numpy as np

MODEL = os.environ.get("VOXFORGE_FAST_STT_MODEL", "Harveenchadha/vakyansh-wav2vec2-hindi-him-4200")
_lock = threading.Lock()
_proc = None
_model = None


def _load():
    global _proc, _model
    if _model is None:
        with _lock:
            if _model is None:
                import torch
                from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
                torch.set_num_threads(int(os.environ.get("VOXFORGE_FAST_STT_THREADS", "4")))
                _proc = Wav2Vec2Processor.from_pretrained(MODEL)
                _model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    return _proc, _model


def warm() -> None:
    """Load the model and run it once, so the first caller does not wait for it."""
    transcribe_pcm(np.zeros(1600, dtype=np.int16).tobytes(), 16000)


def transcribe_pcm(pcm: bytes, sample_rate: int = 16000) -> str:
    """Raw mono 16-bit PCM → Hindi text."""
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
