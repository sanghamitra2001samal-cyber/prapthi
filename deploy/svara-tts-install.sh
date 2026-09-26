#!/usr/bin/env bash
# Deploy svara-TTS the OFFICIAL way (Docker) on a GPU box. Prepared 2026-08-18.
#
# svara-TTS = best fit for Prapthi's Indic catalog: 19 Indian languages incl.
# Telugu + Sanskrit, with REAL emotion via sentence-end tags <happy> <sad>
# <anger> <fear> <surprise>. Model: kenpath/svara-tts-v1 (3B).
#
# HARD REQUIREMENT (from the author's repo): NVIDIA GPU 16GB+ VRAM (24GB rec),
# NVIDIA Container Toolkit, Docker. There is NO CPU path. Will NOT run on the
# current GCP CPU box. Use a RunPod/Lambda/Vast GPU (RunPod ships the NVIDIA
# toolkit, and svara was trained on RunPod — cleanest target).
#
# Run ON the GPU box:  bash svara-tts-install.sh
set -euo pipefail
say(){ printf "\n\033[1m==> %s\033[0m\n" "$1"; }

say "GPU + NVIDIA Container Toolkit present?"
nvidia-smi -L || { echo "NO GPU — abort. svara-TTS requires a 16GB+ VRAM NVIDIA GPU."; exit 1; }
docker info 2>/dev/null | grep -qi nvidia || echo "  WARN: NVIDIA docker runtime not detected — install nvidia-container-toolkit."

say "Clone the official inference server"
cd ~
[ -d svara-tts-inference ] || git clone https://github.com/Kenpath/svara-tts-inference.git
cd svara-tts-inference
[ -f .env.example ] && cp -n .env.example .env || true

say "Start it (downloads kenpath/svara-tts-v1 on first run; OpenAI-compatible API on :8080)"
docker compose up -d || docker-compose up -d
echo "  waiting for the server..."
for i in $(seq 1 60); do curl -sf http://localhost:8080/v1/models >/dev/null 2>&1 && break; sleep 5; done

say "Smoke test — Telugu + Sanskrit WITH emotion (sentence-end tag)"
# Telugu, happy:
curl -s -X POST http://localhost:8080/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"model":"svara-tts-v1","voice":"te_female","input":"మీకు స్వాగతం, మీ రోజు అద్భుతంగా ఉండాలి. <happy>","response_format":"wav"}' \
  --output /tmp/svara_telugu_happy.wav && echo "  -> /tmp/svara_telugu_happy.wav"
# Sanskrit, calm/sad (weaker — less data):
curl -s -X POST http://localhost:8080/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"model":"svara-tts-v1","voice":"sa_male","input":"सर्वे भवन्तु सुखिनः। <sad>","response_format":"wav"}' \
  --output /tmp/svara_sanskrit.wav && echo "  -> /tmp/svara_sanskrit.wav"

say "LICENSE — verify before commercial use"
echo "  https://huggingface.co/kenpath/svara-tts-v1  (confirm commercial use is allowed)"

say "Done — the OpenAI-compatible API is on :8080."
echo "  Next: point a SvaraEngine in engine.py at it (voice = {lang}_{gender}; emotion = <tag> at sentence end)."
echo "  Voices: te_female/te_male (Telugu), sa_female/sa_male (Sanskrit), hi_*, ta_*, ml_*, kn_*, … (38 total)."
