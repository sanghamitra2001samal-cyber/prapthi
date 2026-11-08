"""Builds a voice's training clips from one SYSPIN shard, skipping the recording,
cleaning and Whisper steps: SYSPIN ships studio audio with its own checked
transcripts, which beat anything ASR would produce. Runs ON the training box
inside ~/vcl/.venv, from ~/vcl.

  python prep_syspin.py SPEAKER [MINUTES] [REPO] [SHARD]

SYSPIN_S1.0 (IISc SPIRE lab, Bengaluru) is CC-BY-4.0; the Hugging Face copy used
here is a community re-upload of it. Attribution goes in data/voices/SPEAKER/NOTICE.
"""
import io
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
from huggingface_hub import hf_hub_download
from voice_clone_lab.config import Config, rel_to_root

spk = sys.argv[1]
minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0
repo = sys.argv[3] if len(sys.argv) > 3 else "SayantanJoker/SYSPIN_Hindi_Female_TTS"
shard = sys.argv[4] if len(sys.argv) > 4 else "data/train-00000-of-00035.parquet"

cfg = Config.load()
paths = cfg.paths_for(spk)
sr = cfg.project.sample_rate
lo, hi = cfg.audio.min_chunk_seconds, cfg.audio.max_chunk_seconds
if paths.transcripts_jsonl.exists():
    raise SystemExit(f"{paths.transcripts_jsonl} exists; remove data/voices/{spk} to rebuild")

local = hf_hub_download(repo, shard, repo_type="dataset")
table = pq.read_table(local, columns=["audio", "transcription"])
paths.chunks_dir.mkdir(parents=True, exist_ok=True)
paths.transcripts_jsonl.parent.mkdir(parents=True, exist_ok=True)

rows, total = [], 0.0
for audio, text in zip(table.column("audio").to_pylist(), table.column("transcription").to_pylist()):
    text = (text or "").strip()
    if not text or not audio or not audio.get("bytes"):
        continue
    y, src_sr = sf.read(io.BytesIO(audio["bytes"]), dtype="float32", always_2d=True)
    y = librosa.resample(y.mean(axis=1), orig_sr=src_sr, target_sr=sr)
    y, _ = librosa.effects.trim(y, top_db=cfg.audio.silence_top_db)
    dur = len(y) / sr
    if not lo <= dur <= hi:
        continue
    peak = float(np.abs(y).max())
    if peak > 0.99:                      # clipped take: skip rather than teach the artefact
        continue
    pad = np.zeros(int(cfg.audio.pad_seconds * sr), dtype=np.float32)
    out = paths.chunks_dir / f"{spk}_{len(rows):04d}.wav"
    sf.write(out, np.concatenate([pad, y, pad]), sr, subtype="PCM_16")
    rows.append({"audio": rel_to_root(out), "text": text})
    total += dur
    if total >= minutes * 60:
        break

with paths.transcripts_jsonl.open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
(paths.voice_dir / "NOTICE").write_text(
    f"Training audio: SYSPIN_S1.0 Corpus, SPIRE lab, Indian Institute of Science, Bengaluru.\n"
    f"License: CC-BY-4.0. Taken from {repo} ({shard}).\n", encoding="utf-8")
print(f"{len(rows)} clips, {total / 60:.1f} min -> {paths.chunks_dir}")
if total < 5 * 60:
    raise SystemExit("under 5 minutes of usable clips; pass another SHARD")
