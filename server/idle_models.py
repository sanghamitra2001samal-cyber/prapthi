"""Free models nobody has used for a while.

Every model in this process used to load on first use and stay loaded for
good. Measured on prapthi-1 (32 GB, no swap): about 7 GB just after a restart,
about 20 GB a day later, and on 7 Nov 2026 the kernel killed the app at
20.7 GB. Now each loader calls `touch(name, unload)` on every use, and a
background sweep calls `unload()` for anything idle longer than
PRAPTHI_MODEL_IDLE_S (default 15 minutes). The next request loads it again,
which costs a few seconds once.

`unload()` must be safe against a request that is using the model: callers
hold their own reference while they work (dropping the module's reference
cannot pull the model out from under them), and torch engines take their
lock. It returns False when it could not unload right now (busy); the sweep
tries again next time.
"""
from __future__ import annotations

import ctypes
import gc
import os
import threading
import time
from typing import Callable

IDLE_S = float(os.environ.get("PRAPTHI_MODEL_IDLE_S", "900"))
SWEEP_S = float(os.environ.get("PRAPTHI_MODEL_SWEEP_S", "60"))

_last: dict[str, float] = {}
_unload: dict[str, Callable[[], bool | None]] = {}
_lock = threading.Lock()
_started = False


def touch(name: str, unload: Callable[[], bool | None]) -> None:
    """Record a use of model `name`; `unload` frees it."""
    global _started
    with _lock:
        _last[name] = time.monotonic()
        _unload[name] = unload
        if not _started and IDLE_S > 0:
            _started = True
            threading.Thread(target=_loop, name="idle-models", daemon=True).start()


def is_idle(name: str) -> bool:
    """True if `name` has not been used for IDLE_S (unload() re-checks this
    under its own lock, in case a request touched it after the sweep looked)."""
    with _lock:
        t = _last.get(name)
    return t is None or time.monotonic() - t >= IDLE_S


def loaded() -> dict[str, float]:
    """name -> seconds since last use, for logging."""
    now = time.monotonic()
    with _lock:
        return {n: round(now - t) for n, t in _last.items()}


def _trim() -> None:
    # glibc keeps freed memory in its arenas; hand it back to the system.
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def sweep() -> list[str]:
    now = time.monotonic()
    with _lock:
        idle = [(n, t, _unload[n]) for n, t in _last.items() if now - t >= IDLE_S]
    freed = []
    for name, seen, unload in idle:
        try:
            ok = unload()
        except Exception as e:  # noqa: BLE001 — never kill the sweeper
            print(f"[idle-models] unloading {name} failed: {e!r}", flush=True)
            continue
        if ok is False:
            continue
        with _lock:
            if _last.get(name) == seen:      # not used again since we looked
                del _last[name]
                del _unload[name]
        freed.append(name)
    if freed:
        gc.collect()
        _trim()
        print(f"[idle-models] freed after {IDLE_S:.0f}s idle: {', '.join(freed)}", flush=True)
    return freed


def _loop() -> None:
    while True:
        time.sleep(SWEEP_S)
        try:
            sweep()
        except Exception as e:  # noqa: BLE001
            print(f"[idle-models] sweep failed: {e!r}", flush=True)
