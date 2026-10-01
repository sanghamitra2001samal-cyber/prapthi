#!/usr/bin/env python3
"""Hand the GPU to ACE-Step only while a song or sound effect is being made.

ACE-Step is elastic — left running it expands to fill whatever VRAM is free
(10.1 GB observed, then 7.9 GB) and never gives it back. That is a poor trade:
songs have been generated four times in the platform's life, while IndicF5
serves interactive voice requests where a user is sitting and waiting. So
IndicF5 is the resident tenant and ACE-Step is loaded on demand. It warms in
about 20 seconds, which is nothing against a song that takes minutes.

This listens on the port the platform already calls (8003) and moves the real
ACE-Step service to 8013.

  * /health is answered here, locally, without touching the GPU. The platform
    polls it every minute to decide whether to offer songs at all, and that
    poll must never drag the model in and out of memory.
  * Any real request takes the lock, stops IndicF5, waits for the driver to
    actually release the memory, starts ACE-Step, and proxies.
  * After GPUSWAP_IDLE with nothing arriving, ACE-Step is stopped and IndicF5
    comes back.

While ACE-Step holds the GPU the IndicF5 service is down, and the app box falls
back to its own CPU IndicF5 — slower, but it answers.

Adapted from gpuswap.py, which did the same for the Sanskrit chant voice; the
VRAM-release wait below is the part that matters and is kept as it was.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ACE_PORT, ACE_REAL = 8003, 8013
IF5_HEALTH = "http://127.0.0.1:8004/health"
# The service answers on the port a few seconds before the model is in VRAM,
# so wait for this rather than for a bare 200 — otherwise the first request
# after the GPU comes back pays the warm-up (about 12s).
IF5_WARM = '"loaded": true'
IDLE_BEFORE_REVERT = int(os.environ.get("GPUSWAP_IDLE", "300"))
ACE_READY_TIMEOUT = int(os.environ.get("GPUSWAP_ACE_TIMEOUT", "300"))
IF5_READY_TIMEOUT = int(os.environ.get("GPUSWAP_IF5_TIMEOUT", "240"))

_lock = threading.Lock()
_mode = "if5"          # who holds the GPU right now
_last_used = 0.0


def log(msg: str) -> None:
    print(f"[acedemand] {msg}", flush=True)


def systemctl(*args: str) -> None:
    subprocess.run(["systemctl", *args], capture_output=True, timeout=120)


def gpu_used_mib() -> int:
    """Total VRAM in use, so we can wait for a stopped service to let go."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout.strip()
        return int(out.splitlines()[0])
    except Exception:
        return -1


def wait_for_vram_release(before: int, timeout: int = 60) -> None:
    """Block until the GPU actually gives the memory back.

    systemctl returns as soon as the unit stops, but the driver can take a few
    seconds to reclaim its memory. Starting the other service in that window is
    what caused a generation to fail with CUDA out-of-memory even though the
    swap had "succeeded"."""
    if before < 0:
        time.sleep(5)
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        now = gpu_used_mib()
        if now >= 0 and now < before - 500:      # at least 500 MiB handed back
            log(f"VRAM released: {before} -> {now} MiB")
            return
        time.sleep(2)
    log(f"VRAM still at {gpu_used_mib()} MiB after {timeout}s — continuing anyway")


def _wait_ready(url: str, needle: str | None, timeout: int) -> bool:
    """Poll until the service answers (and, if given, its body contains needle)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=4) as r:
                body = r.read().decode("utf-8", "ignore")
                if r.status == 200 and (needle is None or needle in body):
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def switch_to(target: str) -> bool:
    """Put the GPU into `target` mode. Caller must hold the lock."""
    global _mode
    if _mode == target:
        return True
    before = gpu_used_mib()
    if target == "ace":
        log("handing the GPU to ACE-Step")
        systemctl("stop", "if5")
        wait_for_vram_release(before)
        systemctl("start", "acestep")
        ok = _wait_ready(f"http://127.0.0.1:{ACE_REAL}/health", None,
                         ACE_READY_TIMEOUT)
        if not ok:
            log("ACE-Step did not come up; giving the GPU back to IndicF5")
            systemctl("stop", "acestep")
            wait_for_vram_release(gpu_used_mib())
            systemctl("start", "if5")
            _wait_ready(IF5_HEALTH, IF5_WARM, IF5_READY_TIMEOUT)
            _mode = "if5"
            return False
    else:
        log("returning the GPU to IndicF5")
        systemctl("stop", "acestep")
        wait_for_vram_release(before)
        systemctl("start", "if5")
        if not _wait_ready(IF5_HEALTH, IF5_WARM, IF5_READY_TIMEOUT):
            log("IndicF5 did not come back up — the app box will fall back to CPU")
            _mode = "none"
            return False
    _mode = target
    log(f"mode = {_mode} ({gpu_used_mib()} MiB in use)")
    return True


def idle_watcher() -> None:
    while True:
        time.sleep(15)
        try:
            with _lock:
                if _mode == "ace" and time.time() - _last_used > IDLE_BEFORE_REVERT:
                    log(f"idle {IDLE_BEFORE_REVERT}s — returning the GPU to IndicF5")
                    switch_to("if5")
        except Exception as e:
            log(f"idle watcher: {e!r}")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "acedemand"

    def log_message(self, *a):            # quiet; we do our own logging
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_GET(self):
        # Answered locally, without touching the GPU: the platform polls this
        # every minute to decide whether to offer songs, and that poll must
        # never pull the model in and out of memory.
        if self.path.rstrip("/") in ("", "/health", "/healthz"):
            body = json.dumps({
                "status": "ok", "service": "ace", "gpu_mode": _mode,
                "loaded": True, "managed_by": "acedemand",
            }).encode()
            return self._send(200, body, "application/json")
        return self._proxy()

    def do_POST(self):
        return self._proxy()

    def _proxy(self):
        global _last_used
        with _lock:
            if not switch_to("ace"):
                body = json.dumps({
                    "error": "The GPU could not be handed to the music engine "
                             "in time. Please try again shortly."}).encode()
                return self._send(503, body, "application/json")
            _last_used = time.time()

            length = int(self.headers.get("Content-Length") or 0)
            payload = self.rfile.read(length) if length else None
            req = urllib.request.Request(
                f"http://127.0.0.1:{ACE_REAL}{self.path}",
                data=payload, method=self.command,
                headers={"Content-Type": self.headers.get(
                    "Content-Type", "application/json")})
            try:
                with urllib.request.urlopen(req, timeout=1800) as r:
                    data = r.read()
                    ctype = r.headers.get("Content-Type",
                                          "application/octet-stream")
                    _last_used = time.time()
                    return self._send(r.status, data, ctype)
            except urllib.error.HTTPError as e:
                return self._send(e.code, e.read(),
                                  e.headers.get("Content-Type",
                                                "application/json"))
            except Exception as e:
                body = json.dumps({"error": f"music engine failed: {e!r}"}).encode()
                return self._send(502, body, "application/json")


def main() -> None:
    global _mode
    # Start from the resting state: ACE-Step down, IndicF5 holding the GPU.
    systemctl("stop", "acestep")
    systemctl("start", "if5")
    _mode = "if5" if _wait_ready(IF5_HEALTH, IF5_WARM, IF5_READY_TIMEOUT) else "none"
    log(f"starting in mode {_mode} ({gpu_used_mib()} MiB in use)")
    threading.Thread(target=idle_watcher, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", ACE_PORT), Handler)
    log(f"listening on {ACE_PORT}; real ACE-Step on {ACE_REAL}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
