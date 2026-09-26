#!/usr/bin/env bash
# Install IndexTTS-2 on a GPU VM. Prepared 2026-08-17 (UNTESTED — no GPU yet).
# IndexTTS-2 is the only engine with REAL emotion (measured 3.95 vs <1.0 for the
# rest). It needs an NVIDIA GPU (~6 GB VRAM; the planned L4 has 24 GB).
# Blocked until L4 quota > 0.
#
# Run ON the GPU VM:  bash indextts2-install.sh
set -euo pipefail
say(){ printf "\n\033[1m==> %s\033[0m\n" "$1"; }

say "GPU present?"
nvidia-smi -L || { echo "NO GPU — abort. IndexTTS-2 is unusable on CPU (minutes/clip)."; exit 1; }

say "System packages"
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg libsndfile1 git curl

say "uv (dependency manager IndexTTS-2 requires)"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

say "Clone IndexTTS-2"
cd ~/prapthi
[ -d index-tts ] || git clone https://github.com/index-tts/index-tts.git
cd index-tts
uv sync --all-extras          # Python 3.10/3.11 env + deps (torch CUDA, transformers)

say "Download the model (IndexTTS-2.5, the newest)"
uv run hf download IndexTeam/IndexTTS-2.5 --local-dir=checkpoints \
  || uv run modelscope download --model IndexTeam/IndexTTS-2.5 --local_dir checkpoints

say "Smoke test (needs a 5-10s reference clip at /tmp/ref.wav)"
if [ -f /tmp/ref.wav ]; then
  uv run python - <<'PY'
from indextts.infer_v2 import IndexTTS2
tts = IndexTTS2(cfg_path="checkpoints/config.yaml", model_dir="checkpoints")
tts.infer(spk_audio_prompt="/tmp/ref.wav",
          text="This is a test of real emotional speech.",
          output_path="/tmp/idx_test.wav")
print("OK -> /tmp/idx_test.wav")
PY
else
  echo "  (no /tmp/ref.wav — provide a reference clip to test)"
fi

say "Done — next: microservice on :8011 + IndexTTSEngine in engine.py (see INDEXTTS2-PLAN.md)"
