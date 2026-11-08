"""Renders the A/B test set with the cloning we serve today: IndicF5 given the same
reference clip the Qwen3-TTS systems got. Runs ON the serving GPU box (prapthi-gpu),
against its local :8004, with the same request body server/engine.py sends.
Standard library only.

  python3 baseline_if5.py DIR SENTENCES.json
      DIR holds reference.wav + reference.json; writes DIR/indicf5/<id>_t<k>.wav
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

TAKES = 2   # keep in step with ab_tools.py

d, spec = Path(sys.argv[1]).expanduser(), Path(sys.argv[2])
ref_text = json.loads((d / "reference.json").read_text(encoding="utf-8"))["text"]
out = d / "indicf5"
out.mkdir(exist_ok=True)
for r in json.loads(spec.read_text(encoding="utf-8")):
    for k in range(1, TAKES + 1):
        p = out / f"{r['id']}_t{k}.wav"
        if p.exists():
            continue
        body = {"text": r["text"], "ref_audio_path": str(d / "reference.wav"), "ref_text": ref_text}
        req = urllib.request.Request("http://127.0.0.1:8004/tts", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t = time.time()
        with urllib.request.urlopen(req, timeout=300) as resp:
            p.write_bytes(resp.read())
        print(f"{p.name} {time.time() - t:.1f}s", flush=True)
