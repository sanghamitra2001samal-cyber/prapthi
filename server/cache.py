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


# Bump this whenever a change alters how audio SOUNDS for an unchanged request
# — an engine parameter, a voice's pace, a cloning reference clip. The key does
# not and cannot capture those, so without a bump every existing entry keeps
# serving the old audio forever and the fix looks like it did nothing.
#
# 2 = Piper per-voice pace correction + corrected IndicF5 male reference.
# 3 = mms-hin baseline pitch, so it stops crossing the male/female boundary.
_VERSION = os.environ.get("VOXFORGE_CACHE_VERSION", "4")


def _key(voice_id: str, text: str, rate, pitch, volume) -> str:
    """One key per *render*, not per file format.

    Most engines sample randomly, so asking twice gives two different takes.
    The studio asks twice on purpose — once to play, once for the download —
    and with the format in the key those were two separate renders, so the
    file a customer downloaded was audibly not the one they had just heard.
    Formats of one request now share a key and are converted from each other.
    """
    raw = f"{_VERSION}|{voice_id}|{rate}|{pitch}|{volume}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _transcode(data: bytes, src_ext: str, dst_ext: str) -> bytes | None:
    """Convert one stored render into the other format. Never re-synthesises."""
    import subprocess
    import tempfile
    src = dst = None
    try:
        with tempfile.NamedTemporaryFile(suffix="." + src_ext, delete=False) as f:
            f.write(data)
            src = f.name
        dst = src + "." + dst_ext
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src]
        if dst_ext == "mp3":
            cmd += ["-codec:a", "libmp3lame", "-q:a", "2"]
        cmd.append(dst)
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(dst):
            return None
        with open(dst, "rb") as f:
            return f.read()
    except Exception:
        return None
    finally:
        for q in (src, dst):
            if q and os.path.exists(q):
                try:
                    os.unlink(q)
                except OSError:
                    pass


def get(voice_id, text, rate, pitch, volume, fmt) -> tuple[bytes, str] | None:
    if not _ENABLED:
        return None
    k = _key(voice_id, text, rate, pitch, volume)
    want = "wav" if fmt == "wav" else "mp3"
    p = _DIR / f"{k}.{want}"
    if p.exists():
        try:
            data = p.read_bytes()
            os.utime(p, None)  # bump mtime for LRU
            return data, _MIME[want]
        except OSError:
            return None
    # The same render in the other format: convert it rather than generate a
    # second, different take.
    other = "mp3" if want == "wav" else "wav"
    q = _DIR / f"{k}.{other}"
    if q.exists():
        try:
            src = q.read_bytes()
            os.utime(q, None)
        except OSError:
            return None
        out = _transcode(src, other, want)
        if out is None:
            return None
        try:
            _DIR.mkdir(exist_ok=True)
            p.write_bytes(out)
            _evict()
        except OSError:
            pass  # serving it matters more than keeping it
        return out, _MIME[want]
    return None


def put(voice_id, text, rate, pitch, volume, audio: bytes, mime: str) -> None:
    if not _ENABLED:
        return
    ext = _EXT.get(mime)
    if not ext:
        return
    try:
        _DIR.mkdir(exist_ok=True)
        k = _key(voice_id, text, rate, pitch, volume)
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
