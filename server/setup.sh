#!/usr/bin/env bash
# Optional: install the Piper neural voice (model + Python runtime).
#
# You do NOT need this on macOS — the built-in `say` engine already produces
# real downloadable WAV/MP3 files. Run this only to add the higher-quality
# cross-platform Piper voice (PRD/TRD recommendation).
#
# Piper runs via the `piper-tts` Python package (pip), NOT the prebuilt binary
# — the upstream macOS binary release ships broken (missing bundled dylibs).
# `piper-tts` needs Python 3.12 or 3.13 (onnxruntime has no 3.14 wheel yet).
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p models

# Curated set of the most human-sounding English voices (MIT/Apache models —
# confirm each license before shipping). "high" = larger model, more natural.
B="https://huggingface.co/rhasspy/piper-voices/resolve/main/en"
dl() {  # <stem> <subpath>
  local stem="$1" sub="$2"
  [ -f "models/${stem}.onnx" ] && { echo "have ${stem}"; return; }
  echo "==> Downloading ${stem}…"
  curl -sL "${B}/${sub}/${stem}.onnx"      -o "models/${stem}.onnx"
  curl -sL "${B}/${sub}/${stem}.onnx.json" -o "models/${stem}.onnx.json"
}
dl en_US-lessac-high        en_US/lessac/high          # warm female, top quality
dl en_US-ryan-high          en_US/ryan/high            # natural male
dl en_GB-jenny_dioco-medium en_GB/jenny_dioco/medium   # natural British female
dl en_US-amy-medium         en_US/amy/medium           # clear, lightweight
# --- Indian-language neural voices (Hindi/Telugu/Malayalam) ----------------- #
dl hi_IN-priyamvada-medium  hi/hi_IN/priyamvada/medium # Hindi female
dl hi_IN-rohan-medium       hi/hi_IN/rohan/medium      # Hindi male
dl te_IN-maya-medium        te/te_IN/maya/medium       # Telugu female
dl te_IN-venkatesh-medium   te/te_IN/venkatesh/medium  # Telugu male
dl ml_IN-meera-medium       ml/ml_IN/meera/medium      # Malayalam female
dl ml_IN-arjun-medium       ml/ml_IN/arjun/medium      # Malayalam male
# Add more from https://huggingface.co/rhasspy/piper-voices — any .onnx dropped
# into models/ appears automatically in the picker.

# --- Kokoro: the most human-sounding engine (24 kHz, Apache-2.0) ----------- #
mkdir -p models/kokoro
KR="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
[ -f models/kokoro/kokoro-v1.0.onnx ] || {
  echo "==> Downloading Kokoro model (~310 MB)…"
  curl -sL "$KR/kokoro-v1.0.onnx" -o models/kokoro/kokoro-v1.0.onnx
  curl -sL "$KR/voices-v1.0.bin"  -o models/kokoro/voices-v1.0.bin
}

# Install the runtime into the server venv if present.
if [ -x ".venv/bin/pip" ]; then
  echo "==> Installing kokoro-onnx + piper-tts into .venv…"
  .venv/bin/pip install --quiet kokoro-onnx piper-tts || {
    echo "!! neural engine install failed (need Python 3.12/3.13). The macOS"
    echo "   'say' voices still work; neural voices appear once this succeeds."
  }
fi

# --- Optional: MMS engine for more Indian languages ------------------------ #
# Tamil, Bengali, Kannada, Gujarati, Marathi, Punjabi (Meta MMS-TTS, ~840 MB +
# PyTorch). Opt-in:  ./setup.sh mms   (or WANT_MMS=1 ./setup.sh)
if [ "${1:-}" = "mms" ] || [ "${WANT_MMS:-}" = "1" ]; then
  if [ -x ".venv/bin/pip" ]; then
    echo "==> Installing MMS engine (torch + transformers)…"
    # Intel macOS caps at torch 2.2.2, which needs transformers < 5 and
    # numpy < 2 (torch 2.2.2 is built against the NumPy 1.x ABI). Kokoro/Piper
    # work fine on numpy 1.26 too.
    .venv/bin/pip install --quiet "torch==2.2.2" "transformers>=4.40,<5" "numpy<2"
  fi
  echo "==> Downloading MMS Indian-language models (~840 MB)…"
  .venv/bin/python - <<'PY'
import os
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
from transformers import VitsModel, AutoTokenizer
cache = "models/mms"
for l in ["tam", "ben", "kan", "guj", "mar", "pan"]:
    mid = f"facebook/mms-tts-{l}"
    VitsModel.from_pretrained(mid, cache_dir=cache)
    AutoTokenizer.from_pretrained(mid, cache_dir=cache)
    print("  got", l)
PY
fi

# --- Optional: Parler HD engine (AI4Bharat Indic Parler-TTS) --------------- #
# The most human-sounding open Indian voices (~3.5 GB, CPU-only here so SLOW:
# ~75-95s/sentence). The model is GATED on Hugging Face. Opt-in:
#   1) accept the licence at https://huggingface.co/ai4bharat/indic-parler-tts
#   2) export HF_TOKEN=<a CLASSIC "Read" token>   (fine-grained tokens need
#      "canReadGatedRepos"; a classic Read token works out of the box)
#   3) ./setup.sh parler   (or WANT_PARLER=1 ./setup.sh)
if [ "${1:-}" = "parler" ] || [ "${WANT_PARLER:-}" = "1" ]; then
  if [ -z "${HF_TOKEN:-}" ]; then
    echo "!! Set HF_TOKEN to a classic 'Read' token first (see notes above)."
  elif [ -x ".venv/bin/pip" ]; then
    echo "==> Installing Parler deps (order matters to avoid a build failure)…"
    # parler-tts pulls llvmlite via librosa; install known-good wheels first,
    # then parler-tts --no-deps, then bump protobuf for the T5 tokenizer.
    .venv/bin/pip install --quiet "llvmlite==0.44.0" "numba==0.61.2" \
      sentencepiece accelerate descript-audio-codec
    .venv/bin/pip install --quiet --no-deps \
      git+https://github.com/huggingface/parler-tts.git
    .venv/bin/pip install --quiet "protobuf>=4.25,<5"
    echo "==> Downloading Indic Parler-TTS (~3.5 GB)…"
    .venv/bin/python - <<'PY'
import os, warnings
warnings.filterwarnings("ignore")
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
from parler_tts import ParlerTTSForConditionalGeneration
from transformers import AutoTokenizer
c = "models/parler"
m = ParlerTTSForConditionalGeneration.from_pretrained("ai4bharat/indic-parler-tts", cache_dir=c)
AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts", cache_dir=c)
te = getattr(getattr(m.config, "text_encoder", None), "_name_or_path", None)
if te:
    AutoTokenizer.from_pretrained(te, cache_dir=c)  # description encoder tokenizer
print("  Parler HD ready.")
PY
  fi
fi

echo "==> Done. Start the server: uvicorn app:app  (engines auto-detected)"
