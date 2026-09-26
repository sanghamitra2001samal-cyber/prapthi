"""RVC singing-voice conversion bridge (Applio, fully self-hosted).

ACE-Step generates a song with a (Western-ish) AI voice. To make it sing in an
authentic Indian voice — or the user's own voice — we convert the *vocal stem*
with a trained RVC model via Applio, then remix with the instrumental.

Pipeline (orchestrated in app.py):
  ACE-Step song -> Demucs split (vocals + instrumental)
               -> RVC convert vocals (this module)
               -> remix converted vocals + instrumental -> final song

This module only does the RVC inference + (optional) training kick-off; it shells
out to Applio's CLI inside its own venv so deps stay isolated.
"""

from __future__ import annotations

import glob
import os
import subprocess

APPLIO_DIR = os.environ.get("APPLIO_DIR", "/home/ubuntu/Applio")
APPLIO_PY = os.path.join(APPLIO_DIR, ".venv", "bin", "python")
APPLIO_LOGS = os.path.join(APPLIO_DIR, "logs")

# Built-in voices shipped with the app (model folder name under Applio/logs).
BUILTIN_MODELS = {
    "indian": "indianreal",        # real human Indian female voice (RVC)
    "indian-female": "indianreal",
    "indian-male": "indianmale",   # real human Indian male voice (RVC)
}


class RVCError(RuntimeError):
    pass


def model_dir(model_name: str) -> str:
    return os.path.join(APPLIO_LOGS, model_name)


def resolve_model(voice: str) -> str:
    """Map a UI voice id (e.g. 'indian' or a user model name) to its Applio
    model folder name."""
    return BUILTIN_MODELS.get(voice, voice)


def model_files(model_name: str) -> tuple[str, str | None]:
    """Find the (.pth weight, .index) for a trained model. Picks the newest
    non-discriminator weight."""
    d = model_dir(model_name)
    if not os.path.isdir(d):
        raise RVCError(f"voice model '{model_name}' not found")
    pths = [p for p in glob.glob(os.path.join(d, "*.pth"))
            if not os.path.basename(p).startswith(("G_", "D_"))]
    if not pths:
        # fall back to the exported weight location
        pths = glob.glob(os.path.join(APPLIO_DIR, "logs", model_name, "*.pth"))
    if not pths:
        raise RVCError(f"no trained weight for '{model_name}' yet")
    pth = max(pths, key=os.path.getmtime)
    idxs = glob.glob(os.path.join(d, "*.index"))
    index = max(idxs, key=os.path.getmtime) if idxs else None
    return pth, index


def is_ready(model_name: str) -> bool:
    try:
        model_files(model_name)
        return True
    except RVCError:
        return False


def convert_vocal(
    in_wav: str,
    voice: str,
    out_wav: str,
    *,
    pitch: int = 0,
    index_rate: float = 0.5,
    protect: float = 0.33,
) -> str:
    """Convert a vocal WAV to the target voice. Tuned for *humanized* output:
      - protect=0.33 preserves breaths/consonants (less robotic),
      - index_rate=0.5 balances target timbre vs. artifacts,
      - rmvpe pitch (Applio default) for accurate, natural pitch,
      - light compression + reverb for warmth.
    """
    model_name = resolve_model(voice)
    pth, index = model_files(model_name)
    cmd = [
        APPLIO_PY, "core.py", "infer",
        "--input_path", in_wav,
        "--output_path", out_wav,
        "--pth_path", pth,
        "--pitch", str(int(pitch)),
        "--index_rate", str(index_rate),
        "--protect", str(protect),
        "--volume_envelope", "1",
        "--clean_audio", "True",
        "--clean_strength", "0.4",
        "--export_format", "WAV",
        # subtle warmth so the converted voice sounds human, not sterile
        "--compressor", "True",
        "--reverb", "True",
        "--reverb_wet_gain", "0.12",
        "--reverb_dry_gain", "0.9",
        "--reverb_room_size", "0.3",
    ]
    if index:
        cmd += ["--index_path", index]
    # Clean env: never let the app's PYTHONPATH shadow Applio's own `rvc` package.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        cmd, cwd=APPLIO_DIR, capture_output=True, timeout=600, env=env
    )
    if proc.returncode != 0 or not os.path.exists(out_wav):
        raise RVCError(
            "rvc convert failed: " + proc.stderr.decode("utf-8", "ignore")[-300:]
        )
    return out_wav


def train_model(model_name: str, dataset_dir: str, sample_rate: int = 48000,
                total_epoch: int = 300) -> subprocess.Popen:
    """Kick off training a user voice model from a dataset folder (background).
    48k + more epochs for detailed, humanized output. Returns the Popen handle;
    the caller polls is_ready()/the log."""
    script = f"""#!/bin/bash
cd {APPLIO_DIR}
source .venv/bin/activate
python core.py preprocess --model_name {model_name} --dataset_path {dataset_dir} --sample_rate {sample_rate} --cut_preprocess Automatic --noise_reduction True --noise_reduction_strength 0.5
python core.py extract --model_name {model_name} --sample_rate {sample_rate} --embedder_model contentvec --include_mutes 2 --cpu_cores 4 --gpu 0
python core.py train --model_name {model_name} --sample_rate {sample_rate} --save_every_epoch 50 --total_epoch {total_epoch} --batch_size 6 --gpu 0 --pretrained True --save_only_latest True --overtraining_detector False
python core.py index --model_name {model_name}
echo RVC_TRAIN_DONE
"""
    sh = os.path.join("/tmp", f"rvc_train_{model_name}.sh")
    with open(sh, "w") as f:
        f.write(script)
    log = os.path.join("/tmp", f"rvc_train_{model_name}.log")
    return subprocess.Popen(
        ["bash", sh], stdout=open(log, "w"), stderr=subprocess.STDOUT
    )
