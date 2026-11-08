#!/usr/bin/env bash
# Runs as root, once, ON whichever box trains: a rented VM after `trainbox up`, or
# the serving L4 (`trainbox night-setup`, which already has its driver). Installs the
# headless NVIDIA 595 driver the serving box runs (G4 needs R580+) if missing, ffmpeg,
# and voice_clone_lab at a pinned commit with the Qwen3-TTS 1.7B base weights.
# Leaves running services alone.
#
#   sudo bash setup.sh
set -euo pipefail
VCL_SHA=e0ecf00b2dfea6292b5896b25fd16843a0fb8651   # tetsuo-ai/voice_clone_lab, Apache-2.0
U=ubuntu; H=/home/$U
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

export DEBIAN_FRONTEND=noninteractive
cloud-init status --wait >/dev/null || true
apt-get -o DPkg::Lock::Timeout=300 update -q
apt-get -o DPkg::Lock::Timeout=300 install -y -q ffmpeg sox git tmux python3-venv python3-dev build-essential
if ! nvidia-smi >/dev/null 2>&1; then
    apt-get -o DPkg::Lock::Timeout=300 install -y -q \
        linux-modules-nvidia-595-open-gcp nvidia-utils-595 nvidia-compute-utils-595 libnvidia-compute-595
    apt-mark hold linux-modules-nvidia-595-open-gcp nvidia-utils-595 >/dev/null
    # Prebuilt modules for the running gcp kernel, so no DKMS build and no reboot.
    modprobe nvidia || { log "nvidia module did not load; reboot and rerun"; exit 1; }
    for i in $(seq 30); do nvidia-smi >/dev/null 2>&1 && break; sleep 2; done
fi
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

sudo -u $U -H bash -euo pipefail <<EOF
cd $H
[ -d vcl ] || git clone -q https://github.com/tetsuo-ai/voice_clone_lab.git vcl
cd vcl && git fetch -q origin && git checkout -q $VCL_SHA
python3 -m venv .venv && . .venv/bin/activate
pip install -q -U pip wheel
# cu128 wheels carry Blackwell (sm_120) kernels; install torch first so nothing below swaps it.
pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -q -e .
vcl setup --download
python - <<'PY'
import torch
assert torch.cuda.is_available(), "torch cannot see the GPU"
x = torch.randn(4096, 4096, device="cuda", dtype=torch.bfloat16)
torch.cuda.synchronize(); (x @ x).sum().item()
print("torch", torch.__version__, torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0),
      f"{torch.cuda.get_device_properties(0).total_memory/2**30:.0f} GiB")
PY
vcl check || true
# The scorer's models, fetched now so the GPU window is not spent downloading.
python -c "from huggingface_hub import snapshot_download as d; d('Systran/faster-whisper-large-v3'); d('microsoft/wavlm-base-plus-sv')"
EOF
touch $H/.SETUP_DONE
log "setup done"
