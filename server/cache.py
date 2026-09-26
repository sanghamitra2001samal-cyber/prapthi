"""Disk-backed audio cache.

Synthesis is deterministic-ish per (voice, text, settings, format), and the
heavy Parler "HD" voices take ~70s on CPU — so caching the result makes any
*repeated* phrase (and every voice preview after the first) play back
instantly. Stored as plain audio files under ``.cache/`` with a simple
size-capped LRU eviction. No user text is written — only a hash of it.

Disable with VOXFORGE_CACHE=0; cap size with VOXFORGE_CACHE_MB (default 500).
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

_DIR = Path(__file__).parent / ".cache"
_ENABLED = os.environ.get("VOXFORGE_CACHE", "1") == "1"
_MAX_BYTES = int(os.environ.get("VOXFORGE_CACHE_MB", "500")) * 1024 * 1024

_EXT = {"audio/wav": "wav", "audio/mpeg": "mp3"}
_MIME = {v: k for k, v in _EXT.items()}


def _key(voice_id: str, text: str, rate, pitch, volume, fmt: str) -> str:
    raw = f"{voice_id}|{rate}|{pitch}|{volume}|{fmt}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(voice_id, text, rate, pitch, volume, fmt) -> tuple[bytes, str] | None:
    if not _ENABLED:
        return None
    k = _key(voice_id, text, rate, pitch, volume, fmt)
    for ext, mime in _MIME.items():
        p = _DIR / f"{k}.{ext}"
        if p.exists():
            try:
                data = p.read_bytes()
                os.utime(p, None)  # bump mtime for LRU
                return data, mime
            except OSError:
                return None
    return None


def put(voice_id, text, rate, pitch, volume, fmt, audio: bytes, mime: str) -> None:
    if not _ENABLED:
        return
    ext = _EXT.get(mime)
    if not ext:
        return
    try:
        _DIR.mkdir(exist_ok=True)
        k = _key(voice_id, text, rate, pitch, volume, fmt)
        (_DIR / f"{k}.{ext}").write_bytes(audio)
        _evict()
    except OSError:
        pass  # caching is best-effort


def _evict() -> None:
    """Keep total cache size under the cap, dropping least-recently-used first."""
    files = [p for p in _DIR.glob("*.*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    if total <= _MAX_BYTES:
        return
    for p in sorted(files, key=lambda f: f.stat().st_mtime):  # oldest first
        try:
            total -= p.stat().st_size
            p.unlink()
        except OSError:
            pass
        if total <= _MAX_BYTES:
            break


def stats() -> dict:
    if not _DIR.exists():
        return {"enabled": _ENABLED, "files": 0, "bytes": 0}
    files = [p for p in _DIR.glob("*.*") if p.is_file()]
    return {
        "enabled": _ENABLED,
        "files": len(files),
        "bytes": sum(p.stat().st_size for p in files),
    }


def clear() -> int:
    n = 0
    if _DIR.exists():
        for p in _DIR.glob("*.*"):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n
