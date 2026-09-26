"""Authentication primitives for Prapthi Ai — stateless, stdlib-only.

Storage now lives in PostgreSQL (see db.py); this module is pure crypto/logic:
  * scrypt password hashing (per-user salt, per-record cost params)
  * HMAC-signed session tokens (JWT-style) with expiry + a session "version"
    claim so a password change / logout can revoke outstanding tokens
  * 6-digit email codes (stored only as SHA-256)
  * email + password-strength validation
  * per-IP login rate limiting
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

_DIR = Path(__file__).parent
_SECRET_FILE = _DIR / ".auth_secret"

SESSION_TTL = int(os.environ.get("VOXFORGE_SESSION_TTL", str(12 * 3600)))  # 12h
COOKIE_NAME = "vf_session"
SECURE_COOKIE = os.environ.get("VOXFORGE_SECURE_COOKIE", "0") == "1"
CODE_TTL = int(os.environ.get("VOXFORGE_CODE_TTL", "900"))  # 15 min

# --- password hashing (scrypt) --------------------------------------------- #
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _DKLEN = 2**17, 8, 1, 32


def _hash_password(password: str, salt: bytes, n: int, r: int, p: int) -> str:
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
        dklen=_DKLEN, maxmem=128 * n * r * p * 2,
    )
    return dk.hex()


def hash_record(password: str) -> dict:
    salt = secrets.token_bytes(16)
    return {
        "salt": salt.hex(),
        "hash": _hash_password(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P),
        "n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P,
    }


def verify_password(password: str, record: dict) -> bool:
    try:
        salt = bytes.fromhex(record["salt"])
        expected = record["hash"]
        n = int(record.get("n", 2**14))
        r = int(record.get("r", 8))
        p = int(record.get("p", 1))
    except (KeyError, ValueError, TypeError):
        return False
    return hmac.compare_digest(_hash_password(password, salt, n, r, p), expected)


_DUMMY_RECORD: dict | None = None


def dummy_verify(password: str) -> None:
    """Same-cost check for unknown emails (prevents timing enumeration)."""
    global _DUMMY_RECORD
    if _DUMMY_RECORD is None:
        _DUMMY_RECORD = hash_record("not-a-real-password")
    verify_password(password, _DUMMY_RECORD)


# --- validation ------------------------------------------------------------ #
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email)) and len(email) <= 254


def password_problem(password: str) -> str | None:
    """Return a human message if the password is too weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 200:
        return "Password is too long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must include at least one letter and one number."
    return None


# --- email codes ----------------------------------------------------------- #
def gen_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def gen_password(n: int = 20) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789@#%&*?"
    return "".join(secrets.choice(alphabet) for _ in range(n))


# --- session tokens (HMAC-signed) ------------------------------------------ #
def _secret() -> bytes:
    if _SECRET_FILE.exists():
        try:
            return bytes.fromhex(_SECRET_FILE.read_text().strip())
        except (OSError, ValueError):
            pass
    s = secrets.token_bytes(32)
    try:
        _SECRET_FILE.write_text(s.hex())
        os.chmod(_SECRET_FILE, 0o600)
    except OSError:
        pass
    return s


_SIGNING_KEY = _secret()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(email: str, version: int) -> str:
    payload = {"sub": email, "exp": int(time.time()) + SESSION_TTL, "v": int(version)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_SIGNING_KEY, body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def decode_token(token: str | None) -> dict | None:
    """Verify signature + expiry; return the payload (incl. sub, v) or None.
    The session-version check against the DB happens in the app layer."""
    if not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    expected = hmac.new(_SIGNING_KEY, body.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_b64d(sig), expected):
            return None
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    if not payload.get("sub"):
        return None
    return payload


# --- rate limiting --------------------------------------------------------- #
_attempts: dict[str, deque[float]] = defaultdict(deque)
_MAX_ATTEMPTS = int(os.environ.get("VOXFORGE_LOGIN_MAX", "10"))
_WINDOW = 300


def login_blocked(key: str) -> bool:
    now = time.time()
    q = _attempts[key]
    while q and now - q[0] > _WINDOW:
        q.popleft()
    return len(q) >= _MAX_ATTEMPTS


def record_attempt(key: str) -> None:
    _attempts[key].append(time.time())


def clear_attempts(key: str) -> None:
    _attempts.pop(key, None)
