"""Vāgdhenu microservice (prathoshap/vagdhenu — Sanskrit chant / pārāyaṇa TTS).

Runs in its own venv/checkout (Python 3.10 + torch cu121 + BigVGAN) so its deps
never touch the main app or the IF5/ACE-Step services. Vāgdhenu *chants* metered
Sanskrit verse (ślokas) with a melodic contour — not flat read-aloud — using a
flow-matching DiT (~337M) + BigVGAN-v2 vocoder. It renders retroflex conjuncts
(ṣṭ, ḍḍh…) faithfully (MOS ~4.6).

The upstream model ships a CLI (``src/render.py``) that consumes a *shard* JSON
and writes ``{outdir}/{id}_{meter}.wav``; there is no importable Python API. So
this wrapper builds a one-verse shard, shells out to that CLI inside the model's
own venv, and returns the resulting WAV.

Config (env):
  VAGDHENU_DIR   path to the cloned vagdhenu repo (contains src/render.py)
  VAGDHENU_PY    python executable of the vagdhenu venv (default: <DIR>/.venv/bin/python)
  VAGDHENU_PORT  port to serve on (default 8006)

Endpoints:
  GET  /health -> {status, loaded, dir}
  POST /chant  -> {text, meter?, seed?} => audio/wav
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VAGDHENU_DIR = Path(os.environ.get("VAGDHENU_DIR", str(Path.home() / "vagdhenu")))
VAGDHENU_PY = os.environ.get(
    "VAGDHENU_PY", str(VAGDHENU_DIR / ".venv" / "bin" / "python")
)
RENDER = VAGDHENU_DIR / "src" / "render.py"
DEFAULT_METER = os.environ.get("VAGDHENU_METER", "anushtubh")

_LOCK = threading.Lock()


def _ready() -> bool:
    return RENDER.exists() and Path(VAGDHENU_PY).exists()


def _split_padas(text: str) -> list[str]:
    """Split verse text into padas (quarter-lines). Honour explicit newlines /
    daṇḍas; fall back to the whole line as a single pada."""
    raw = text.replace("॥", "\n").replace("।", "\n").splitlines()
    padas = [ln.strip() for ln in raw if ln.strip()]
    return padas or [text.strip()]


def _chant(text: str, meter: str, seed: int, no_sandhi: bool = True) -> bytes:
    """Render one verse to WAV bytes via the upstream render.py CLI."""
    if not _ready():
        raise RuntimeError(
            f"vagdhenu not installed (expected {RENDER} and {VAGDHENU_PY})"
        )
    meter = (meter or DEFAULT_METER).strip() or DEFAULT_METER
    vid = "v"
    with _LOCK, tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        shard = tmp_p / "shard.json"
        results = tmp_p / "res.json"
        outdir = tmp_p / "out"
        outdir.mkdir(parents=True, exist_ok=True)
        shard.write_text(
            json.dumps(
                [{
                    "id": vid,
                    "meter": meter,
                    "padas": _split_padas(text),
                    "seed": int(seed),
                    # render.py indexes clip["no_sandhi"] directly — required.
                    "no_sandhi": bool(no_sandhi),
                    "out": vid,
                }]
            ),
            encoding="utf-8",
        )
        cmd = [
            VAGDHENU_PY, str(RENDER),
            "--shard", str(shard),
            "--results", str(results),
            "--outdir", str(outdir),
        ]
        # BigVGAN is imported via PYTHONPATH (it is not pip-installed).
        env = dict(os.environ)
        bigvgan = VAGDHENU_DIR / "BigVGAN"
        env["PYTHONPATH"] = (
            f"{bigvgan}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(bigvgan)
        )
        proc = subprocess.run(
            cmd, cwd=str(VAGDHENU_DIR), capture_output=True, text=True,
            timeout=600, env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"render.py failed ({proc.returncode}): {proc.stderr[-400:]}"
            )
        # With --outdir, render.py writes <outdir>/<id>.wav; be lenient anyway.
        wavs = sorted(outdir.glob("*.wav"))
        if not wavs:
            raise RuntimeError(f"render.py produced no WAV: {proc.stdout[-300:]}")
        preferred = outdir / f"{vid}.wav"
        wav = preferred if preferred.exists() else wavs[0]
        return wav.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json(200, {
                "status": "ok",
                "loaded": _ready(),
                "dir": str(VAGDHENU_DIR),
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path != "/chant":
                return self._json(404, {"error": "not found"})
            text = str(body.get("text", "")).strip()
            if not text:
                return self._json(400, {"error": "text required"})
            audio = _chant(
                text,
                str(body.get("meter", DEFAULT_METER)),
                int(body.get("seed", 0)),
                no_sandhi=bool(body.get("no_sandhi", True)),
            )
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        except Exception as e:  # pragma: no cover
            self._json(500, {"error": repr(e)[:300]})

    def log_message(self, *a):  # silence default logging
        pass


if __name__ == "__main__":
    port = int(os.environ.get("VAGDHENU_PORT", "8006"))
    print(
        f"[vagdhenu] serving on 127.0.0.1:{port} "
        f"(dir={VAGDHENU_DIR}, ready={_ready()})",
        flush=True,
    )
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
