"""VoxForge backend — stateless self-hosted TTS service.

Implements the TRD §5.2 contract using Starlette (no third-party TTS API,
no database, no user-text persistence). Endpoints:

    GET  /health      liveness probe
    GET  /voices      list self-hosted voices
    POST /synthesize  text -> audio file (WAV always; MP3 if ffmpeg present)
    POST /preview     short sample for a voice
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import contextlib
import os
import subprocess
import uuid
from pathlib import Path
import time
from collections import defaultdict, deque

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

import auth
import cache
import db
import email_service
import dubbing
import hinglish
import rvcbridge
import sargam
import song as songmod
from engine import (
    EngineError,
    chatterbox_synth,
    if5_synth,
    load_engine,
    vagdhenu_synth,
)

# Serialize synthesis (torch models aren't safe to run concurrently) while
# still running it off the event loop, so /health etc. stay responsive.
_synth_lock = asyncio.Lock()
# Bound how many requests may wait on that lock — prevents queue-flooding DoS
# where many slow (Parler ~70s) requests pile up unbounded.
_MAX_QUEUE = int(os.environ.get("VOXFORGE_MAX_QUEUE", "4"))
_synth_waiting = 0

CHAR_CAP = int(os.environ.get("VOXFORGE_CHAR_CAP", "5000"))
# Public emotion ids accepted by /synthesize (Parler HD acts on them).
import billing
import emotion as emotion_mod
import entitlements
import voice_names
import expressive_dsp

_EMOTIONS = emotion_mod.EMOTIONS
# Emotion -> prosody multipliers (speed, pitch, volume) layered on top of the
# user's sliders AND any model-level emotion, so feeling comes through on EVERY
# engine (incl. Kokoro/Piper/MMS which have no native emotion).
# Speed deltas kept small so Emotion Intensity changes TONE (pitch/volume),
# not noticeably the speaking rate (QA #2). Pitch carries the feeling.
_EMOTION_PROSODY = {k: f.prosody for k, f in emotion_mod.FEELS.items()}


# --- Speech text normalization (QA #1 phone numbers, #7 punctuation) -------- #
_DIGIT_RUN = re.compile(r"\d{7,}")
_REPEAT_PUNCT = re.compile(r"([,;:.!?।])\1+")
_NONSPEECH = re.compile(r"[*_~^`|<>{}\\=+#@]+")


def normalize_speech_text(text: str) -> str:
    """Clean user text so TTS sounds right:
    * long digit runs (phone numbers/IDs) are read digit-by-digit
    * repeated punctuation is collapsed (avoids 'heee' artifacts)
    * stray non-speech symbols are stripped
    """
    text = _DIGIT_RUN.sub(lambda m: " ".join(m.group(0)), text)
    text = _NONSPEECH.sub(" ", text)
    text = _REPEAT_PUNCT.sub(r"\1", text)
    # space after sentence/number commas; collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text
ALLOWED_ORIGIN = os.environ.get("VOXFORGE_ALLOWED_ORIGIN", "*")
RATE_LIMIT = int(os.environ.get("VOXFORGE_RATE_LIMIT", "60"))  # req/min/IP
# Preview = each voice introduces itself by name, in its own language. (A voice
# can only read its own script, so the template is localized and the brand
# "Prapthi Ai" is transliterated per language.)
PREVIEW_TEMPLATES = {
    "en": "I am {n}. I am the voice from Prapthi Ai. How are you?",
    "hi": "मैं {n} हूँ। मैं Prapthi Ai की आवाज़ हूँ। आप कैसे हैं?",
    "ta": "நான் {n}. நான் Prapthi Ai இன் குரல். நீங்கள் எப்படி இருக்கிறீர்கள்?",
    "te": "నేను {n}. నేను Prapthi Ai నుండి వచ్చిన స్వరం. మీరు ఎలా ఉన్నారు?",
    "bn": "আমি {n}। আমি Prapthi Ai-এর কণ্ঠস্বর। আপনি কেমন আছেন?",
    "kn": "ನಾನು {n}. ನಾನು Prapthi Ai ಧ್ವನಿ. ನೀವು ಹೇಗಿದ್ದೀರಿ?",
    "gu": "હું {n} છું. હું Prapthi Aiનો અવાજ છું. તમે કેમ છો?",
    "mr": "मी {n} आहे. मी Prapthi Aiचा आवाज आहे. तुम्ही कसे आहात?",
    "pa": "ਮੈਂ {n} ਹਾਂ। ਮੈਂ Prapthi Ai ਦੀ ਆਵਾਜ਼ ਹਾਂ। ਤੁਸੀਂ ਕਿਵੇਂ ਹੋ?",
    "ml": "ഞാൻ {n} ആണ്. ഞാൻ Prapthi Ai യുടെ ശബ്ദമാണ്. സുഖമാണോ?",
    # Sanskrit (Devanagari) — Aryan is the sole recommended AI4Bharat speaker.
    "sa": "अहं {n} अस्मि। अहं Prapthi Ai इत्यस्य वाणी अस्मि। भवान् कथमस्ति?",
    # Chatterbox multilingual languages
    "es": "Soy {n}. Soy la voz de Prapthi Ai. ¿Cómo estás?",
    "fr": "Je suis {n}. Je suis la voix de Prapthi Ai. Comment allez-vous ?",
    "de": "Ich bin {n}. Ich bin die Stimme von Prapthi Ai. Wie geht es dir?",
    "it": "Sono {n}. Sono la voce di Prapthi Ai. Come stai?",
    "pt": "Eu sou {n}. Sou a voz da Prapthi Ai. Como você está?",
    "ru": "Я {n}. Я голос Prapthi Ai. Как дела?",
    "zh": "我是{n}。我是 Prapthi Ai 的声音。你好吗？",
    "ja": "私は{n}です。Prapthi Ai の声です。お元気ですか？",
    "ko": "저는 {n}입니다. 저는 Prapthi Ai의 목소리입니다. 어떻게 지내세요?",
    "ar": "أنا {n}. أنا صوت Prapthi Ai. كيف حالك؟",
    "tr": "Ben {n}. Ben Prapthi Ai'nin sesiyim. Nasılsın?",
    "pl": "Jestem {n}. Jestem głosem Prapthi Ai. Jak się masz?",
    "nl": "Ik ben {n}. Ik ben de stem van Prapthi Ai. Hoe gaat het?",
    "sv": "Jag är {n}. Jag är rösten från Prapthi Ai. Hur mår du?",
    "da": "Jeg er {n}. Jeg er stemmen fra Prapthi Ai. Hvordan har du det?",
    "no": "Jeg er {n}. Jeg er stemmen til Prapthi Ai. Hvordan går det?",
    "fi": "Olen {n}. Olen Prapthi Ai:n ääni. Mitä kuuluu?",
    "el": "Είμαι ο {n}. Είμαι η φωνή του Prapthi Ai. Τι κάνεις;",
    "he": "אני {n}. אני הקול של Prapthi Ai. מה שלומך?",
    "ms": "Saya {n}. Saya suara Prapthi Ai. Apa khabar?",
    "sw": "Mimi ni {n}. Mimi ni sauti ya Prapthi Ai. Habari yako?",
}


def _clean_name(display: str) -> str:
    return display.split(" (")[0].split(" · ")[0].strip()


ENGINE = load_engine()
# Warm the (slow, static) voice list once at startup so the first /voices
# request returns instantly instead of timing out the client probe.
_WARM = ENGINE.list_voices()
# Map voiceId -> (language prefix, clean display name) for /preview.
_VOICE_META = {
    v.id: (v.lang.split("-")[0].lower(), _clean_name(v.name)) for v in _WARM
}
print(f"[voxforge] engine: {ENGINE.name} ({len(_WARM)} voices)")


def _warmup() -> None:
    """Pre-load the default fast engine in the background so the *first* real
    request isn't slowed by a cold model load. Only warms thread-safe engines
    (Kokoro/onnxruntime or macOS `say`) — never the torch ones, so it can't
    race a concurrent request. Fully guarded: any failure is ignored.
    Disable with VOXFORGE_WARMUP=0.
    """
    if os.environ.get("VOXFORGE_WARMUP", "1") != "1":
        return

    def _warm_one(voice_id: str) -> None:
        ENGINE.synthesize(
            text="ok", voice_id=voice_id, rate=1.0, pitch=1.0, volume=1.0, fmt="wav"
        )
        print(f"[voxforge] warm-up complete via '{voice_id}'")

    # 1) Fast default engine first (quick — makes the common path instant ASAP).
    try:
        fast = next(
            (v.id for v in _WARM if "Kokoro" in v.name or v.id in _MACOS_SAFE),
            None,
        )
        if fast:
            _warm_one(fast)
    except Exception as e:  # never let warm-up affect server health
        print(f"[voxforge] fast warm-up skipped: {e!r}")

    # 2) Parler HD (heavy, ~140s, holds ~4GB) — opt-out via VOXFORGE_WARMUP_PARLER=0.
    #    Safe because torch engines serialize on _TORCH_LOCK inside the engine,
    #    so this background load can't race a real request.
    if os.environ.get("VOXFORGE_WARMUP_PARLER", "1") == "1":
        try:
            parler = next((v.id for v in _WARM if "Parler" in v.name), None)
            if parler:
                _warm_one(parler)
        except Exception as e:
            print(f"[voxforge] parler warm-up skipped: {e!r}")


# macOS `say` voice ids are plain names (no engine suffix) and are subprocess-
# based (safe to run off-lock); used only as a warm-up fallback.
_MACOS_SAFE = {
    v.id for v in _WARM if "(" not in v.name and "·" not in v.name
}

import threading  # noqa: E402

threading.Thread(target=_warmup, daemon=True).start()

# --- naive in-memory token bucket per IP (TRD §5.4) ----------------------- #
_hits: dict[str, deque[float]] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


# --- auth ------------------------------------------------------------------ #
async def _current_user(request: Request) -> dict | None:
    """Return the authenticated user row, or None. Validates the cookie's
    signature/expiry AND that its session version still matches the DB
    (so logout / password change revoke it) and the account is verified."""
    payload = auth.decode_token(request.cookies.get(auth.COOKIE_NAME))
    if not payload:
        return None
    user = await db.get_user(payload["sub"])
    if not user or not user["is_verified"]:
        return None
    if int(payload.get("v", 0)) != int(user["session_version"]):
        return None
    return user


def _unauthorized() -> JSONResponse:
    return JSONResponse({"error": "authentication required"}, status_code=401)


async def _read_json(request: Request) -> dict | None:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else None
    except Exception:
        return None


def _set_session_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.SESSION_TTL,
        httponly=True,
        samesite="strict",
        secure=auth.SECURE_COOKIE,
        path="/",
    )


# Generic OK message used wherever we must not reveal whether an email exists.
_GENERIC_SENT = {"ok": True, "message": "If that email is eligible, a code was sent."}


async def signup(request: Request) -> JSONResponse:
    ip = _client_ip(request)
    if auth.login_blocked("signup:" + ip):
        return JSONResponse({"error": "too many attempts, try again later"}, 429)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not auth.is_valid_email(email):
        return JSONResponse({"error": "Enter a valid email address."}, status_code=400)
    problem = auth.password_problem(password)
    if problem:
        return JSONResponse({"error": problem}, status_code=400)

    auth.record_attempt("signup:" + ip)
    existing = await db.get_user(email)
    if existing and existing["is_verified"]:
        # Don't reveal that a verified account exists; behave like success.
        return JSONResponse(_GENERIC_SENT)
    if not existing:
        await db.create_user(email, auth.hash_record(password))
    else:
        # Unverified re-signup: refresh the password so they can complete it.
        await db.set_password(email, auth.hash_record(password))

    code = auth.gen_code()
    await db.store_code(email, "verify", auth.hash_code(code), auth.CODE_TTL)
    email_service.send_verification(email, code)
    return JSONResponse({"ok": True, "message": "Verification code sent."})


async def verify_email(request: Request) -> JSONResponse:
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = str(body.get("email", "")).strip().lower()
    code = str(body.get("code", "")).strip()
    if not (email and code):
        return JSONResponse({"error": "email and code required"}, status_code=400)
    if not await db.consume_code(email, "verify", auth.hash_code(code)):
        return JSONResponse({"error": "Invalid or expired code."}, status_code=400)
    await db.mark_verified(email)
    email_service.send_welcome(email)
    return JSONResponse({"ok": True, "message": "Email verified. You can sign in."})


async def resend_code(request: Request) -> JSONResponse:
    ip = _client_ip(request)
    if auth.login_blocked("resend:" + ip):
        return JSONResponse({"error": "too many attempts, try again later"}, 429)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = str(body.get("email", "")).strip().lower()
    auth.record_attempt("resend:" + ip)
    user = await db.get_user(email)
    if user and not user["is_verified"]:
        code = auth.gen_code()
        await db.store_code(email, "verify", auth.hash_code(code), auth.CODE_TTL)
        email_service.send_verification(email, code)
    return JSONResponse(_GENERIC_SENT)


async def login(request: Request) -> JSONResponse:
    ip = _client_ip(request)
    if auth.login_blocked(ip):
        return JSONResponse(
            {"error": "too many attempts, try again later"}, status_code=429
        )
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = str(body.get("email", body.get("username", ""))).strip().lower()
    password = str(body.get("password", ""))

    user = await db.get_user(email)
    if not user:
        auth.dummy_verify(password)  # constant-time-ish
        auth.record_attempt(ip)
        return JSONResponse({"error": "Invalid email or password."}, status_code=401)
    if not auth.verify_password(password, db.password_record(user)):
        auth.record_attempt(ip)
        return JSONResponse({"error": "Invalid email or password."}, status_code=401)
    if not user["is_verified"]:
        return JSONResponse(
            {"error": "unverified", "message": "Please verify your email first."},
            status_code=403,
        )
    auth.clear_attempts(ip)
    await db.touch_login(email)
    email_service.send_login_alert(email)
    resp = JSONResponse(
        {"ok": True, "user": email, "is_admin": bool(user["is_admin"])}
    )
    _set_session_cookie(resp, auth.issue_token(email, user["session_version"]))
    return resp


async def logout(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if user:
        # Revoke server-side so the token can't be replayed after logout.
        await db.bump_session_version(user["email"])
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


async def me(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    return JSONResponse({"user": user["email"], "is_admin": bool(user["is_admin"])})


async def forgot_password(request: Request) -> JSONResponse:
    ip = _client_ip(request)
    if auth.login_blocked("forgot:" + ip):
        return JSONResponse({"error": "too many attempts, try again later"}, 429)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = str(body.get("email", "")).strip().lower()
    auth.record_attempt("forgot:" + ip)
    user = await db.get_user(email)
    if user:  # only send to real accounts, but always return generic
        code = auth.gen_code()
        await db.store_code(email, "reset", auth.hash_code(code), auth.CODE_TTL)
        email_service.send_reset(email, code)
    return JSONResponse(_GENERIC_SENT)


async def reset_password(request: Request) -> JSONResponse:
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    email = str(body.get("email", "")).strip().lower()
    code = str(body.get("code", "")).strip()
    password = str(body.get("password", ""))
    problem = auth.password_problem(password)
    if problem:
        return JSONResponse({"error": problem}, status_code=400)
    if not await db.consume_code(email, "reset", auth.hash_code(code)):
        return JSONResponse({"error": "Invalid or expired code."}, status_code=400)
    # set_password also revokes all existing sessions for the account.
    await db.set_password(email, auth.hash_record(password))
    await db.mark_verified(email)  # a successful reset also proves email ownership
    return JSONResponse({"ok": True, "message": "Password updated. You can sign in."})


# --- handlers -------------------------------------------------------------- #
async def health(request: Request) -> JSONResponse:
    # Public probe stays minimal; expose stack/cache detail only to authed users.
    body: dict = {"status": "ok"}
    if await _current_user(request):
        body["engine"] = ENGINE.name
        body["cache"] = cache.stats()
    return JSONResponse(body)


# IndicF5 HD voices (near-human, served by the :8004 microservice). Each maps
# to a reference clip + its transcript under if5_refs/.
IF5_REF_DIR = Path(__file__).parent / "if5_refs"
IF5_VOICES = {
    "if5-aanya": ("Aanya · Hindi (IndicF5 HD)", "hi-IN", "female", "female"),
    "if5-aarav": ("Aarav · Hindi (IndicF5 HD)", "hi-IN", "male", "male"),
    # Clear, well-pronounced Sanskrit *speech* (not chanting). Auto-hidden until
    # a Sanskrit reference clip (if5_refs/sanskrit.wav + .txt) is present.
    "if5-sanskrit": ("Aryan · Sanskrit (IndicF5 HD)", "sa-IN", "male", "sanskrit"),
}

# Vāgdhenu — Sanskrit *chant* (pārāyaṇa) voice, served by the :8005 microservice.
# Chants metered ślokas with a melodic contour. Gated behind VAGDHENU_ENABLED so
# the voice is only advertised where the (GPU-only) model is actually deployed.
VAGDHENU_VOICES = {
    "vagdhenu-sa-chant": ("Vāgdhenu · Sanskrit (Chant)", "sa-IN", "male"),
}

# Voices not owned by the composite ENGINE (IF5 + Vāgdhenu) still need a language
# for the preview greeting; map id -> (2-letter lang, display name for {n}).
_EXTRA_VOICE_META = {
    vid: (lang.split("-")[0].lower(), disp.split(" · ")[0])
    for vid, (disp, lang, _g, _b) in IF5_VOICES.items()
}
_EXTRA_VOICE_META.update({
    vid: (lang.split("-")[0].lower(), disp.split(" · ")[0])
    for vid, (disp, lang, _g) in VAGDHENU_VOICES.items()
})

# Sanskrit voices must NOT be run through the romanized-Hindi -> Devanagari
# converter (that dictionary is Hindi-specific and would mangle Sanskrit).
SANSKRIT_VOICES = {"if5-sanskrit", "vagdhenu-sa-chant"}


def _if5_ref(voice_id: str) -> tuple[str, str] | None:
    """Return (ref_audio_path, ref_text) for an IndicF5 voice id."""
    meta = IF5_VOICES.get(voice_id)
    if not meta:
        return None
    base = meta[3]
    wav = IF5_REF_DIR / f"{base}.wav"
    txt = IF5_REF_DIR / f"{base}.txt"
    if not wav.exists():
        return None
    ref_text = txt.read_text().strip() if txt.exists() else ""
    return str(wav), ref_text



def _curate_voices(data: list[dict]) -> list[dict]:
    """Hide slow Parler voices where a faster engine covers the same language.

    Parler measures 23-46s per clip on CPU vs 0.6-2s for MMS/Piper/Kokoro, so it
    is a poor default. It is retained for languages nothing else covers, so
    curation never removes a language. Disable with PRAPTHI_CURATE=0.
    """
    if os.environ.get("PRAPTHI_CURATE", "1") != "1":
        return data
    fast_langs = {v["lang"] for v in data if not str(v["id"]).startswith("parler-")}
    return [
        v for v in data
        if not str(v["id"]).startswith("parler-") or v["lang"] not in fast_langs
    ]


async def voices(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    data = [
        {"id": v.id, "name": v.name, "lang": v.lang, "gender": v.gender}
        for v in ENGINE.list_voices()
    ]
    # IndicF5 HD voices (only if the reference clips exist on disk).
    for vid, (name, lang, gender, _b) in IF5_VOICES.items():
        if _if5_ref(vid):
            data.append({"id": vid, "name": name, "lang": lang, "gender": gender})
    # Vāgdhenu Sanskrit chant voice (only where the GPU model is deployed).
    if os.environ.get("VAGDHENU_ENABLED", "0") == "1":
        for vid, (name, lang, gender) in VAGDHENU_VOICES.items():
            data.append({"id": vid, "name": name, "lang": lang, "gender": gender})
    # Append this user's private cloned voices (powered by Chatterbox).
    try:
        for c in await db.list_clones(user["email"]):
            if c["lang"] == "if5":
                data.append({
                    "id": f"if5clone:{c['id']}",
                    "name": f"{c['name']} (IndicF5 HD Clone)",
                    "lang": "hi-IN", "gender": "neutral",
                })
            else:
                data.append({
                    "id": f"clone:{c['id']}",
                    "name": f"{c['name']} (Cloned, Expressive)",
                    "lang": c["lang"], "gender": "neutral",
                })
    except Exception as e:  # never break the picker over clones
        print(f"[voxforge] list clones failed: {e!r}")
    data = _curate_voices(data)
    # Mark what this account may actually use, so the studio can show a lock
    # instead of letting someone click into a refusal. Still a plain array —
    # the studio and the public site both iterate this response directly.
    _feats = entitlements.features(await db.get_account(user["email"]))
    # Customers see a person, not the engine behind it. One pass over the whole
    # catalogue so no two voices in a language can end up sharing a name.
    _named = voice_names.pretty_all(
        [(str(v["id"]), str(v.get("name") or ""), str(v.get("lang") or "en"),
          str(v.get("gender") or "female")) for v in data])
    for v in data:
        v["name"] = _named.get(str(v["id"]), v.get("name"))
        v["premium"] = entitlements.is_premium_voice(str(v["id"]))
        v["locked"] = v["premium"] and not _feats["premium_voices"]
    return JSONResponse(data)


async def clone_create(request: Request) -> JSONResponse:
    """Create a cloned voice from an uploaded audio sample (raw body; name/lang
    as query params). Owner-scoped and capped per user."""
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    name = (request.query_params.get("name") or "").strip()[:40]
    lang = (request.query_params.get("lang") or "en").lower()
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    if lang not in _CLONE_LANGS:
        lang = "en"
    _acct = await db.get_account(user["email"])
    _plan = entitlements.effective_plan(_acct)
    _limit = entitlements.clone_limit(_acct)
    if await db.count_clones(user["email"]) >= _limit:
        return JSONResponse(
            {"error": entitlements.clone_limit_message(_plan, _limit),
             "code": "upgrade_required"},
            status_code=402,
        )
    raw = await request.body()
    if not raw or len(raw) < 2000:
        return JSONResponse({"error": "audio sample required"}, status_code=400)

    CLONE_DIR.mkdir(exist_ok=True)
    vid = uuid.uuid4().hex
    out = CLONE_DIR / f"{vid}.wav"
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        src = tf.name
        tf.write(raw)
    try:
        # Normalize to 24 kHz mono WAV, capped at 30s — robust reference for cloning.
        proc = await run_in_threadpool(
            subprocess.run,
            ["ffmpeg", "-y", "-i", src, "-t", "30", "-ac", "1", "-ar", "24000",
             str(out)],
            capture_output=True,
        )
        if proc.returncode != 0 or not out.exists():
            return JSONResponse(
                {"error": "could not process that audio file"}, status_code=400
            )
    finally:
        if os.path.exists(src):
            os.unlink(src)

    await db.add_clone(vid, user["email"], name, lang, str(out))
    return JSONResponse(
        {
            "id": f"clone:{vid}",
            "name": f"{name} (Cloned, Expressive)",
            "lang": lang,
            "gender": "neutral",
        }
    )


async def if5_clone_create(request: Request) -> JSONResponse:
    """Clone a voice with IndicF5: upload a clip, auto-transcribe it (Whisper),
    and store it as a reusable voice that speaks 11 Indian languages."""
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    name = (request.query_params.get("name") or "").strip()[:40]
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    _acct = await db.get_account(user["email"])
    _plan = entitlements.effective_plan(_acct)
    _limit = entitlements.clone_limit(_acct)
    if await db.count_clones(user["email"]) >= _limit:
        return JSONResponse(
            {"error": entitlements.clone_limit_message(_plan, _limit),
             "code": "upgrade_required"},
            status_code=402,
        )
    raw = await request.body()
    if not raw or len(raw) < 2000:
        return JSONResponse({"error": "audio sample required"}, status_code=400)
    CLONE_DIR.mkdir(exist_ok=True)
    vid = uuid.uuid4().hex
    out = CLONE_DIR / f"if5_{vid}.wav"
    import tempfile as _tf
    with _tf.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        src = tf.name
        tf.write(raw)
    try:
        proc = await run_in_threadpool(
            subprocess.run,
            ["ffmpeg", "-y", "-i", src, "-t", "30", "-ac", "1", "-ar", "24000", str(out)],
            capture_output=True)
        if proc.returncode != 0 or not out.exists():
            return JSONResponse({"error": "could not process that audio"}, status_code=400)
    finally:
        if os.path.exists(src):
            os.unlink(src)
    # Auto-transcribe the reference clip (IndicF5 needs the prompt's text).
    ref_text = (request.query_params.get("ref_text") or "").strip()
    if not ref_text:
        try:
            segs, _lang = await run_in_threadpool(dubbing.transcribe, str(out))
            ref_text = " ".join(s["text"] for s in segs)[:400]
        except Exception as e:
            print(f"[if5clone] transcribe failed: {e!r}")
    if not ref_text:
        ref_text = "namaste"
    out.with_suffix(".txt").write_text(ref_text)
    await db.add_clone(vid, user["email"], name, "if5", str(out))
    return JSONResponse({
        "id": f"if5clone:{vid}",
        "name": f"{name} (IndicF5 HD Clone)",
        "lang": "hi-IN", "gender": "neutral", "ref_text": ref_text,
    })


async def clone_delete(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    vid = request.path_params["vid"]
    path = await db.delete_clone(vid, user["email"])
    if not path:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# EmotionSong — script -> song (API-free: MusicGen beat + emotional TTS vocals)
# --------------------------------------------------------------------------- #
SONGS_DIR = Path(__file__).parent / "songs_out"
_MAX_SONG_JOBS = int(os.environ.get("VOXFORGE_MAX_SONG_JOBS", "2"))
_song_jobs_running = 0


async def song_extract(request: Request) -> JSONResponse:
    """Extract text from an uploaded TXT/PDF/DOCX (raw body, ?type=)."""
    if not await _current_user(request):
        return _unauthorized()
    kind = (request.query_params.get("type") or "txt").lower()
    raw = await request.body()
    if not raw:
        return JSONResponse({"error": "empty file"}, status_code=400)
    try:
        text = await run_in_threadpool(songmod.extract_text, raw, kind)
    except Exception as e:
        print(f"[song] extract failed: {e!r}")
        return JSONResponse({"error": "Could not read that file."}, status_code=400)
    text = (text or "").strip()[:60000]
    if not text:
        return JSONResponse(
            {"error": "No readable text found in the file."}, status_code=400
        )
    return JSONResponse({"text": text, "words": len(text.split())})


async def song_analyze(request: Request) -> JSONResponse:
    if not await _current_user(request):
        return _unauthorized()
    body = await _read_json(request) or {}
    script = str(body.get("script", "")).strip()
    if len(script.split()) < 5:
        return JSONResponse(
            {"error": "Add a longer script (at least a sentence or two)."},
            status_code=400,
        )
    script = script[:60000]
    title = (str(body.get("title", "")).strip() or "Untitled")[:80]
    emo = await run_in_threadpool(songmod.analyze_emotion, script)
    lyrics = await run_in_threadpool(songmod.build_lyrics, script, title)
    return JSONResponse({"emotion": emo, "lyrics": lyrics, "title": title})


async def song_create(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    if _song_jobs_running >= _MAX_SONG_JOBS:
        return JSONResponse(
            {"error": "Song generator busy — try again in a minute."},
            status_code=503,
        )
    body = await _read_json(request) or {}
    script = str(body.get("script", "")).strip()
    if len(script.split()) < 5:
        return JSONResponse({"error": "Script too short."}, status_code=400)
    if not _capabilities_now().get("ace"):
        return JSONResponse(
            {"error": "The music generator is offline right now. "
                      "Nothing has been charged — please try again later."},
            status_code=503,
        )
    _refused = await _charge(user["email"], "song")
    if _refused is not None:
        return _refused
    script = script[:60000]
    title = (str(body.get("title", "")).strip() or "Untitled")[:80]
    genre = str(body.get("genre", "pop")).lower()[:30]
    language = str(body.get("language", "en")).lower()[:10]
    vocals = str(body.get("vocals", body.get("voiceId", "female"))).strip().lower()
    if vocals not in ("female", "male", "duet"):
        vocals = "female"
    try:
        duration = float(body.get("duration", 30) or 30)
    except (TypeError, ValueError):
        duration = 30.0
    mood = str(body.get("mood", "")).strip().lower()
    singer_style = str(body.get("singer_style", "")).strip().lower()[:20]
    musical_key = str(body.get("musical_key", "")).strip()[:12]
    try:
        bpm = int(body.get("bpm")) if body.get("bpm") else None
    except (TypeError, ValueError):
        bpm = None
    # "Sing in a chosen voice" — reference audio from one of the user's own
    # uploaded/cloned voices (rights-gated to voices they own).
    ref_voice_id = str(body.get("ref_voice_id", "")).strip()
    # Optional explicit instrument arrangement picks.
    raw_instr = body.get("instruments") or []
    instruments = [str(x).strip().lower()[:30] for x in raw_instr if str(x).strip()][:12] \
        if isinstance(raw_instr, list) else []
    ref_audio_path = None
    ref_strength = 0.5
    ref_audio_temp = False
    if ref_voice_id:
        rc = await db.get_clone(ref_voice_id.split(":")[-1], user["email"])
        if rc:
            ref_audio_path = rc["path"]
    # "Melody guide" — render a Sargam/solfège/letter melody and condition the
    # sung song on it (audio-to-audio) so the vocals follow the chosen tune.
    # Takes precedence over the voice clone since both use the single ref slot.
    melody_spec = body.get("melody") or {}
    if isinstance(melody_spec, dict) and str(melody_spec.get("notation", "")).strip():
        try:
            wav = await run_in_threadpool(
                sargam.render,
                str(melody_spec["notation"])[:8000],
                str(melody_spec.get("system", "auto")),
                str(melody_spec.get("tonic", musical_key or "C")).split()[0] or "C",
                str(melody_spec.get("instrument", "concert flute")),
                int(melody_spec.get("bpm", bpm or 90) or 90),
                "wav",
            )
        except sargam.NotationError as e:
            return JSONResponse({"error": f"Melody: {e}"}, status_code=400)
        guides = SONGS_DIR / "guides"
        guides.mkdir(parents=True, exist_ok=True)
        gp = str(guides / f"{uuid.uuid4().hex}.wav")
        with open(gp, "wb") as f:
            f.write(wav)
        # Loop the guide to the song length (audio-to-audio truncates to ref len).
        try:
            _dur = float(body.get("duration", 30) or 30)
        except (TypeError, ValueError):
            _dur = 30.0
        _loop_audio_to(gp, _dur)
        ref_audio_path = gp
        ref_audio_temp = True
        try:
            ref_strength = max(0.2, min(float(melody_spec.get("strength", 0.6)), 0.9))
        except (TypeError, ValueError):
            ref_strength = 0.6
    lyrics = str(body.get("lyrics", "")).strip()
    emo = await run_in_threadpool(songmod.analyze_emotion, script)
    dominant = mood or str(body.get("emotion", "")).strip().lower() or emo["dominant"]
    if not lyrics:
        lyrics = await run_in_threadpool(songmod.build_lyrics, script, title)

    # NOTE: We deliberately do NOT seed Indian-language songs with a looped TTS
    # speech reference — ACE-Step is a text-to-song model and conditioning it on
    # looped speech injects harsh artifacts. Authentic Hindi comes from native
    # Devanagari lyrics + a strong Hindi/Bollywood prompt instead.

    sid = uuid.uuid4().hex
    await db.create_song(
        sid, user["email"], title, script, lyrics, genre, language,
        vocals, dominant, json.dumps(emo["scores"]),
    )
    asyncio.create_task(
        _run_song_job(
            sid, user["email"],
            {"lyrics": lyrics, "genre": genre, "vocals": vocals,
             "emotion": dominant, "duration": duration, "language": language,
             "singer_style": singer_style, "bpm": bpm, "musical_key": musical_key,
             "instruments": instruments,
             "ref_audio_path": ref_audio_path, "ref_strength": ref_strength,
             "ref_audio_temp": ref_audio_temp,
             "rvc_voice": str(body.get("rvc_voice", "")).strip() or None,
             "seed": None},
        )
    )
    return JSONResponse({"id": sid})


# Indian-language songs get an Indian-voice reference (Kokoro Hindi voices give
# authentic Indian timbre; the lyrics carry the actual language).
_INDIAN_LANGS = {"hi", "hinglish", "te", "ta", "pa"}
_INDIAN_REF_VOICE = {
    "female": "hf_alpha",   # Aria · Hindi
    "male": "hm_omega",     # Arjun · Hindi
}


def _loop_audio_to(path: str, seconds: float) -> None:
    """Loop a WAV in place to ~`seconds` so it spans the whole song. ACE-Step's
    audio-to-audio truncates output to the reference length, so the reference
    must be at least as long as the target song."""
    try:
        out = path + ".loop.wav"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-stream_loop", "-1", "-i", path,
             "-t", str(max(8.0, float(seconds))), out],
            capture_output=True,
        )
        if proc.returncode == 0 and os.path.exists(out):
            os.replace(out, path)
        elif os.path.exists(out):
            os.unlink(out)
    except Exception:
        pass  # best-effort


def _indian_voice_ref(
    lyrics: str, language: str, vocals: str, duration: float
) -> str | None:
    """Render an Indian-voice sample from the lyrics (native Devanagari), loop it
    to the song length, and save as a temp WAV to use as the ACE-Step voice
    reference — so the singer has authentic Indian timbre/diction."""
    try:
        dev = songmod.prepare_song_lyrics(lyrics, language)
        # a couple of lyric lines (skip section tags) make the timbre reference
        lines = [ln.strip() for ln in dev.splitlines()
                 if ln.strip() and not ln.strip().startswith("[")]
        sample = " ".join(lines)[:240]
        if not sample:
            return None
        voice = _INDIAN_REF_VOICE.get(
            "male" if (vocals or "").lower() == "male" else "female"
        )
        wav, _mime = ENGINE.synthesize(
            text=sample, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav"
        )
        guides = SONGS_DIR / "guides"
        guides.mkdir(parents=True, exist_ok=True)
        gp = str(guides / f"ref_{uuid.uuid4().hex}.wav")
        with open(gp, "wb") as f:
            f.write(wav)
        _loop_audio_to(gp, duration)
        return gp
    except Exception as e:  # never block song creation over the reference
        print(f"[song] indian voice ref failed: {e!r}")
        return None


def _rvc_song_voice(sid: str, mp3_path: str, voice: str) -> str | None:
    """Re-voice a finished song in an Indian RVC voice: split the vocal with
    Demucs, convert it with RVC, and remix over the instrumental. Returns the
    new mp3 path (overwrites the song) or None on failure. NOTE: this swaps the
    vocal *timbre* only — the singing/pronunciation stays as ACE-Step sang it."""
    work = str(SONGS_DIR / f"{sid}_rv")
    try:
        os.makedirs(work, exist_ok=True)
        songmod.acestep_stems(mp3_path, work, "rv")
        voc_mp3 = os.path.join(work, "rv_vocals.mp3")
        inst_mp3 = os.path.join(work, "rv_instrumental.mp3")
        if not (os.path.exists(voc_mp3) and os.path.exists(inst_mp3)):
            return None
        voc_wav = os.path.join(work, "voc.wav")
        subprocess.run(["ffmpeg", "-y", "-i", voc_mp3, voc_wav], capture_output=True)
        conv = os.path.join(work, "conv.wav")
        rvcbridge.convert_vocal(voc_wav, voice, conv)
        out = os.path.join(work, "final.mp3")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", conv, "-i", inst_mp3, "-filter_complex",
             "[0:a]volume=1.1[v];[1:a]volume=0.85[m];"
             "[v][m]amix=inputs=2:duration=longest:normalize=0,dynaudnorm=f=200[a]",
             "-map", "[a]", "-b:a", "192k", out],
            capture_output=True,
        )
        if proc.returncode != 0 or not os.path.exists(out):
            return None
        os.replace(out, mp3_path)   # overwrite the song with the re-voiced mix
        return mp3_path
    except Exception as e:
        print(f"[song] rvc re-voice failed: {e!r}")
        return None
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


async def _run_song_job(sid: str, owner: str, p: dict) -> None:
    """Generate a full sung song via ACE-Step (lyrics + style prompt)."""
    global _song_jobs_running
    _song_jobs_running += 1
    try:
        await db.update_song(sid, status="processing", progress=15,
                             current_step="Writing lyrics")
        prompt = songmod.song_prompt(
            p["genre"], p["emotion"], p["vocals"],
            singer_style=p.get("singer_style", ""), bpm=p.get("bpm"),
            musical_key=p.get("musical_key", ""), language=p.get("language", "en"),
            instruments=p.get("instruments"),
        )
        # Native-script lyrics (romanized Hindi -> Devanagari) for clean singing.
        lang_lyrics = songmod.prepare_song_lyrics(p["lyrics"], p.get("language", "en"))
        ace_lyrics = songmod.lyrics_for_acestep(lang_lyrics)
        dur = max(15.0, min(p["duration"], 120.0))
        # SFT/Base quality: 50 steps for maximum vocal nuance & clarity
        # (per ACE-Step's musician guide; ~8-9s on the L4).
        infer_steps = 50

        await db.update_song(sid, progress=45, current_step="Composing song")
        # Serialize GPU use against TTS so the box never OOMs.
        async with _synth_lock:
            wav = await run_in_threadpool(
                songmod.acestep_song, prompt, ace_lyrics, dur, infer_steps,
                p.get("ref_audio_path"), p.get("ref_strength", 0.5), p.get("seed"),
            )

        await db.update_song(sid, progress=90, current_step="Finalizing")
        mp3 = await run_in_threadpool(songmod.wav_to_mp3, wav)

        SONGS_DIR.mkdir(exist_ok=True)
        path = str(SONGS_DIR / f"{sid}.mp3")
        with open(path, "wb") as f:
            f.write(mp3)

        # Optional: re-voice the song in an Indian RVC voice (timbre only).
        rvc_voice = p.get("rvc_voice")
        if rvc_voice and rvcbridge.is_ready(rvcbridge.resolve_model(rvc_voice)):
            await db.update_song(sid, progress=95, current_step="Applying Indian voice")
            await run_in_threadpool(_rvc_song_voice, sid, path, rvc_voice)

        await db.update_song(
            sid, status="done", progress=100, current_step="Completed",
            audio_path=path, duration_seconds=int(dur),
        )
    except Exception as e:
        print(f"[song] job {sid} failed: {e!r}")
        await db.update_song(sid, status="failed", current_step="Failed",
                             error=repr(e)[:300])
        # Songs are charged up front; give it back when one does not arrive.
        try:
            async with db.pool.connection() as _c:
                _row = await (await _c.execute(
                    "SELECT owner FROM songs WHERE id = %s", (sid,))).fetchone()
            if _row:
                _owed = entitlements.op_cost("song")
                await db.refund_chars(_row["owner"], _owed)
                print(f"[song] refunded {_owed} characters to {_row['owner']}")
        except Exception as _re:
            print(f"[song] REFUND FAILED for {sid}: {_re!r}")
    finally:
        _song_jobs_running -= 1
        # Clean up a temporary melody-guide render (clone paths are persistent).
        if p.get("ref_audio_temp") and p.get("ref_audio_path"):
            try:
                os.unlink(p["ref_audio_path"])
            except OSError:
                pass


def _song_row_json(row: dict) -> dict:
    return {
        k: (v.isoformat() if hasattr(v, "isoformat") else v)
        for k, v in row.items()
        if k not in ("script",)
    }


async def song_status(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    row = await db.get_song(request.path_params["sid"], user["email"])
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(_song_row_json(row))


async def song_list(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    rows = await db.list_songs(user["email"])
    return JSONResponse([_song_row_json(r) for r in rows])


async def song_audio(request: Request) -> Response:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    row = await db.get_song(request.path_params["sid"], user["email"])
    if not row or not row.get("audio_path") or not os.path.exists(row["audio_path"]):
        return JSONResponse({"error": "not ready"}, status_code=404)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", row.get("title") or "song")[:40]
    return FileResponse(
        row["audio_path"], media_type="audio/mpeg", filename=f"{safe}.mp3"
    )


async def song_delete(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    path = await db.delete_song(request.path_params["sid"], user["email"])
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass
    return JSONResponse({"ok": True})


# --- Regenerate (new take) + versioning ------------------------------------ #
async def song_regenerate(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    if _song_jobs_running >= _MAX_SONG_JOBS:
        return JSONResponse({"error": "busy — try again shortly"}, status_code=503)
    row = await db.get_song(request.path_params["sid"], user["email"])
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    body = await _read_json(request) or {}
    # optionally regenerate fresh lyrics from the original script
    lyrics = row["lyrics"]
    if body.get("new_lyrics"):
        lyrics = await run_in_threadpool(
            songmod.build_lyrics, row["script"], row["title"]
        )
    new = uuid.uuid4().hex
    parent = row.get("parent_id") or row["id"]
    await db.create_song(
        new, user["email"], f"{row['title']} (new take)", row["script"], lyrics,
        row["genre"], row["language"], row["voice_id"], row["emotion"],
        row["emotion_json"], parent_id=parent,
    )
    asyncio.create_task(
        _run_song_job(new, user["email"], {
            "lyrics": lyrics, "genre": row["genre"], "vocals": row["voice_id"],
            "emotion": row["emotion"], "duration": row["duration_seconds"] or 40,
            "language": row["language"], "seed": random.randint(1, 2_000_000_000),
        })
    )
    return JSONResponse({"id": new})


# --- Stems / karaoke / instrumental (Demucs) ------------------------------- #
_STEM_KINDS = {"vocals", "instrumental", "drums", "bass", "other"}


def _wav_file_to_mp3(wav_path: str, mp3_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-ac", "2", "-ar", "44100",
         "-b:a", "192k", mp3_path],
        capture_output=True,
    )


async def _run_stems(sid: str, audio_path: str) -> None:
    try:
        # Service writes final <sid>_<stem>.mp3 directly into SONGS_DIR.
        await run_in_threadpool(
            songmod.acestep_stems, audio_path, str(SONGS_DIR), sid
        )
        await db.update_song(sid, stems_status="done")
    except Exception as e:
        print(f"[song] stems {sid} failed: {e!r}")
        await db.update_song(sid, stems_status="failed")


async def song_stems(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    row = await db.get_song(request.path_params["sid"], user["email"])
    if not row or row.get("status") != "done" or not row.get("audio_path"):
        return JSONResponse({"error": "song not ready"}, status_code=400)
    if row.get("stems_status") == "processing":
        return JSONResponse({"stems_status": "processing"})
    await db.update_song(row["id"], stems_status="processing")
    asyncio.create_task(_run_stems(row["id"], row["audio_path"]))
    return JSONResponse({"stems_status": "processing"})


async def song_stem_file(request: Request) -> Response:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    sid = request.path_params["sid"]
    kind = request.path_params["kind"]
    if kind not in _STEM_KINDS:
        return JSONResponse({"error": "bad stem"}, status_code=400)
    if not await db.get_song(sid, user["email"]):
        return _unauthorized()
    p = SONGS_DIR / f"{sid}_{kind}.mp3"
    if not p.exists():
        return JSONResponse({"error": "not ready"}, status_code=404)
    return FileResponse(str(p), media_type="audio/mpeg", filename=f"{kind}.mp3")


# --- Sargam / notation melody engine (FluidSynth, exact notes) ------------- #
async def melody_summary(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    body = await _read_json(request) or {}
    try:
        info = await run_in_threadpool(
            sargam.notation_summary,
            str(body.get("notation", ""))[:8000],
            str(body.get("system", "auto")),
            str(body.get("tonic", "C")),
        )
        return JSONResponse(info)
    except sargam.NotationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:  # pragma: no cover
        return JSONResponse({"error": repr(e)[:200]}, status_code=400)


async def melody_render(request: Request) -> Response:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    body = await _read_json(request) or {}
    notation = str(body.get("notation", "")).strip()[:8000]
    if not notation:
        return JSONResponse({"error": "Enter a melody first."}, status_code=400)
    try:
        bpm = int(body.get("bpm", 90) or 90)
    except (TypeError, ValueError):
        bpm = 90
    try:
        audio = await run_in_threadpool(
            sargam.render,
            notation,
            str(body.get("system", "auto")),
            str(body.get("tonic", "C")),
            str(body.get("instrument", "grand piano")),
            bpm,
            "mp3",
        )
    except sargam.NotationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:  # pragma: no cover
        return JSONResponse({"error": repr(e)[:200]}, status_code=500)
    return Response(
        content=audio, media_type="audio/mpeg",
        headers={"Content-Disposition": 'inline; filename="melody.mp3"'},
    )


# --- AI Dubbing (Whisper -> M2M-100 -> Parler TTS -> timed mux) ------------- #
DUB_DIR = Path(__file__).parent / "dubs"
_dub_jobs: dict = {}
_dub_lock = threading.Lock()
# target language -> default Parler dubbing voice
DUB_VOICE = {
    "hi": "parler-hi-divya", "ta": "parler-ta-jaya", "kn": "parler-kn-anu",
    "ml": "parler-ml-anjali", "bn": "parler-bn-aditi", "mr": "parler-mr-sunita",
    "gu": "parler-gu-neha", "pa": "parler-pa-gurpreet", "or": "parler-or-debjani",
    "ne": "parler-ne-amrita", "te": "parler-te-lalitha", "as": "parler-as-amit",
    "en": "af_heart",
}
DUB_LANG_NAMES = {
    "hi": "Hindi", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam",
    "bn": "Bengali", "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi",
    "or": "Odia", "ne": "Nepali", "te": "Telugu", "as": "Assamese", "en": "English",
}
_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _run_dub_pipeline(jid: str, in_path: str, ext: str, tgt: str,
                      voice: str, keep_bg: float) -> None:
    """Heavy dubbing work (runs in a threadpool)."""
    import tempfile as _tf
    try:
        _dub_jobs[jid].update(status="processing", step="Extracting audio", progress=10)
        is_video = ext in _VIDEO_EXT
        wav = str(DUB_DIR / f"{jid}_src.wav")
        dubbing.extract_audio(in_path, wav)

        _dub_jobs[jid].update(step="Transcribing (Whisper)", progress=30)
        segs, src_lang = dubbing.transcribe(wav)
        if not segs:
            raise RuntimeError("no speech detected")

        _dub_jobs[jid].update(step="Translating", progress=50)
        texts = [s["text"] for s in segs]
        tr = dubbing.translate(texts, src_lang, tgt)
        for s, t in zip(segs, tr):
            s["text_tgt"] = t

        _dub_jobs[jid].update(step="Re-voicing", progress=70)

        def tts_fn(text: str) -> str:
            wavb, _m = ENGINE.synthesize(
                text=text, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")
            p = _tf.mktemp(suffix=".wav")
            with open(p, "wb") as f:
                f.write(wavb)
            return p

        dub_wav = str(DUB_DIR / f"{jid}_dub.wav")
        dubbing.assemble_dub(segs, tts_fn, dub_wav)

        # Optional music bed: Demucs-separate the ORIGINAL into music (no speech)
        # so the source speaker's voice doesn't bleed under the dub.
        final_audio = dub_wav
        if keep_bg > 0:
            try:
                _dub_jobs[jid].update(step="Extracting background music", progress=82)
                bgsrc = str(DUB_DIR / f"{jid}_bgsrc.wav")
                subprocess.run(["ffmpeg", "-y", "-i", in_path, "-ac", "2",
                                "-ar", "44100", bgsrc], capture_output=True)
                songmod.acestep_stems(bgsrc, str(DUB_DIR), f"{jid}bg")
                inst = str(DUB_DIR / f"{jid}bg_instrumental.mp3")
                if os.path.exists(inst):
                    mixed = str(DUB_DIR / f"{jid}_mixed.wav")
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", dub_wav, "-i", inst, "-filter_complex",
                         f"[1:a]volume={keep_bg}[bg];[0:a]volume=1.0[v];"
                         "[v][bg]amix=inputs=2:duration=longest:normalize=0[a]",
                         "-map", "[a]", mixed], capture_output=True)
                    if os.path.exists(mixed):
                        final_audio = mixed
                for f in (bgsrc, inst):
                    try:
                        os.unlink(f)
                    except OSError:
                        pass
            except Exception as e:
                print(f"[dub] bg music step skipped: {e!r}")

        _dub_jobs[jid].update(step="Finalizing", progress=92)
        if is_video:
            out = str(DUB_DIR / f"{jid}.mp4")
            dubbing.mux_audio_to_video(in_path, final_audio, out, keep_bg=0.0)
        else:
            out = str(DUB_DIR / f"{jid}.mp3")
            subprocess.run(["ffmpeg", "-y", "-i", final_audio, "-b:a", "192k", out],
                           capture_output=True)
        _dub_jobs[jid].update(
            status="done", step="Completed", progress=100, out=out,
            is_video=is_video,
            transcript=[{"t": s["text"], "tr": s["text_tgt"]} for s in segs],
        )
    except Exception as e:
        import traceback as _tb
        print(f"[dub] {jid} failed: {e!r}\n{_tb.format_exc()}")
        # The customer paid up front for work that did not happen.
        _owed = _dub_jobs.get(jid, {}).get("charged", 0)
        _who = _dub_jobs.get(jid, {}).get("owner")
        if _owed and _who:
            try:
                asyncio.run_coroutine_threadsafe(
                    db.refund_chars(_who, _owed), _LOOP).result(timeout=10)
                print(f"[dub] refunded {_owed} characters to {_who}")
            except Exception as _re:
                print(f"[dub] REFUND FAILED for {_who}: {_re!r}")
        _dub_jobs[jid].update(status="failed", step="Failed", error=repr(e)[:300])
    finally:
        for p in (in_path, str(DUB_DIR / f"{jid}_src.wav"),
                  str(DUB_DIR / f"{jid}_dub.wav")):
            try:
                os.unlink(p)
            except OSError:
                pass


async def _charge(email: str, op: str, seconds: float = 1.0):
    # The owner is not billed for their own platform.
    _acct = await db.get_account(email)
    if _acct and _acct.get("is_admin"):
        return None
    """Charge an operation against the monthly allowance.

    Returns None when it went through, or a JSONResponse to return to the
    caller when there is not enough left. Charged up front, before the work
    starts, so nobody gets a free render by disconnecting."""
    await db.reset_period_if_due(email)
    need = entitlements.op_cost(op, seconds)
    ok, remaining = await db.consume_chars(email, need)
    if ok:
        return None
    account = await db.get_account(email)
    left = max(0, int(account["chars_allowance"]) - int(account["chars_used"]))
    return JSONResponse(
        {"error": entitlements.too_expensive_message(op, need, left),
         "code": "quota_exceeded", "need": need, "left": left},
        status_code=402,
    )


async def dub_create(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"error": "No file uploaded."}, status_code=400)
    tgt = str(form.get("target_lang", "hi")).lower()
    if tgt not in DUB_VOICE:
        return JSONResponse({"error": f"Unsupported language '{tgt}'."}, status_code=400)
    voice = str(form.get("voice", "")).strip() or DUB_VOICE[tgt]
    try:
        keep_bg = max(0.0, min(float(form.get("keep_bg", 0) or 0), 1.0))
    except (TypeError, ValueError):
        keep_bg = 0.0
    ext = os.path.splitext(getattr(upload, "filename", "") or "")[1].lower() or ".mp4"
    data = await upload.read()
    if len(data) > 200 * 1024 * 1024:
        return JSONResponse({"error": "File too large (max 200MB)."}, status_code=400)
    DUB_DIR.mkdir(exist_ok=True)
    jid = uuid.uuid4().hex
    in_path = str(DUB_DIR / f"{jid}_in{ext}")
    with open(in_path, "wb") as f:
        f.write(data)
    # Charge for the length actually submitted, before the pipeline starts.
    _secs = dubbing._dur(in_path)
    _refused = await _charge(user["email"], "dub", _secs)
    if _refused is not None:
        try:
            os.remove(in_path)
        except OSError:
            pass
        return _refused
    _dub_jobs[jid] = {"status": "queued", "step": "Queued", "progress": 0,
                      "owner": user["email"], "target": tgt,
                      "charged": entitlements.op_cost("dub", _secs)}
    asyncio.create_task(run_in_threadpool(
        _run_dub_pipeline, jid, in_path, ext, tgt, voice, keep_bg))
    return JSONResponse({"id": jid})


async def dub_status(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _dub_jobs.get(request.path_params["jid"])
    if not j or j.get("owner") != user["email"]:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({k: v for k, v in j.items() if k not in ("out", "owner")})


async def dub_file(request: Request) -> Response:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _dub_jobs.get(request.path_params["jid"])
    if not j or j.get("owner") != user["email"] or j.get("status") != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    out = j["out"]
    media = "video/mp4" if j.get("is_video") else "audio/mpeg"
    fn = "dubbed" + os.path.splitext(out)[1]
    return FileResponse(out, media_type=media, filename=fn)


# --- Conversational Voice Agent (Whisper -> LLM -> TTS) -------------------- #
AGENT_SYS = (
    "You are Prapthi, a warm, friendly Indian voice assistant. Reply naturally "
    "and concisely in the SAME language the user used (Hindi in Devanagari, or "
    "English). Keep replies short and conversational — they will be spoken aloud. "
    "Be helpful for everyday and small-business tasks."
)


def _llm_chat(messages: list, max_tokens: int = 220) -> str:
    import urllib.request
    url = os.environ.get("LLM_URL", "http://127.0.0.1:8005") + "/chat"
    req = urllib.request.Request(
        url, data=json.dumps({"messages": messages, "max_tokens": max_tokens}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["reply"]


def _agent_tts(text: str) -> bytes:
    """Speak the agent's reply: IndicF5 (Hindi) for Devanagari, else English TTS."""
    if re.search(r"[ऀ-ॿ]", text):
        ref = _if5_ref("if5-aanya")
        if ref:
            audio, _m = if5_synth(text, ref[0], ref[1], fmt="mp3")
            return audio
    audio, _m = ENGINE.synthesize(
        text=text, voice_id="af_heart", rate=1.0, pitch=1.0, volume=1.0, fmt="mp3")
    return audio


def _agent_turn(history: list, user_text: str) -> tuple[str, str]:
    """Run one turn: returns (reply_text, audio_data_uri)."""
    import base64
    msgs = [{"role": "system", "content": AGENT_SYS}]
    for m in history[-12:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": str(m["content"])[:2000]})
    # The "Indian assistant" persona pulls replies into Hindi even when the
    # user wrote English. The rule has to ride on the user turn: a trailing
    # system message was measured to be ignored by the model.
    hindi = any("\u0900" <= ch <= "\u097f" for ch in user_text)
    rule = "(Reply in Hindi, Devanagari.)" if hindi else "(Reply in English only.)"
    msgs.append({"role": "user", "content": user_text + "\n\n" + rule})
    reply = _llm_chat(msgs)
    audio = _agent_tts(reply)
    uri = "data:audio/mpeg;base64," + base64.b64encode(audio).decode()
    return reply, uri


async def agent_chat(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    body = await _read_json(request) or {}
    text = str(body.get("text", "")).strip()[:2000]
    if not text:
        return JSONResponse({"error": "empty message"}, status_code=400)
    history = body.get("history") or []
    try:
        reply, uri = await run_in_threadpool(_agent_turn, history, text)
    except Exception as e:
        return JSONResponse({"error": repr(e)[:200]}, status_code=500)
    return JSONResponse({"transcript": text, "reply": reply, "audio": uri})


async def agent_voice(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"error": "no audio"}, status_code=400)
    history = []
    try:
        history = json.loads(form.get("history") or "[]")
    except Exception:
        history = []
    import tempfile as _tf
    src = _tf.mktemp(suffix=".webm")
    wav = _tf.mktemp(suffix=".wav")
    with open(src, "wb") as f:
        f.write(await upload.read())

    def _work():
        dubbing.extract_audio(src, wav)
        segs, _lang = dubbing.transcribe(wav)
        user_text = " ".join(s["text"] for s in segs).strip()
        if not user_text:
            return None
        reply, uri = _agent_turn(history, user_text)
        return user_text, reply, uri

    try:
        res = await run_in_threadpool(_work)
    except Exception as e:
        return JSONResponse({"error": repr(e)[:200]}, status_code=500)
    finally:
        for p in (src, wav):
            try:
                os.unlink(p)
            except OSError:
                pass
    if not res:
        return JSONResponse({"error": "could not hear anything"}, status_code=400)
    user_text, reply, uri = res
    return JSONResponse({"transcript": user_text, "reply": reply, "audio": uri})


# --- Sound Effects (AudioLDM2 via the ACE service) ------------------------- #
SFX_DIR = Path(__file__).parent / "sfx_out"
_sfx_jobs: dict = {}


def _run_sfx(jid: str, prompt: str, duration: float) -> None:
    try:
        _sfx_jobs[jid].update(status="processing", step="Generating", progress=30)
        wav = songmod.acestep_sfx(prompt, duration)
        SFX_DIR.mkdir(exist_ok=True)
        out = str(SFX_DIR / f"{jid}.mp3")
        mp3 = songmod.wav_to_mp3(wav)
        with open(out, "wb") as f:
            f.write(mp3)
        _sfx_jobs[jid].update(status="done", step="Completed", progress=100, out=out)
    except Exception as e:
        print(f"[sfx] {jid} failed: {e!r}")
        # Charged up front, so hand it back when the work did not happen.
        _owed = _sfx_jobs.get(jid, {}).get("charged", 0)
        _who = _sfx_jobs.get(jid, {}).get("owner")
        if _owed and _who:
            try:
                asyncio.run_coroutine_threadsafe(
                    db.refund_chars(_who, _owed), _LOOP).result(timeout=10)
                print(f"[sfx] refunded {_owed} characters to {_who}")
            except Exception as _re:
                print(f"[sfx] REFUND FAILED for {_who}: {_re!r}")
        _sfx_jobs[jid].update(status="failed", step="Failed", error=repr(e)[:200])


async def sfx_create(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    body = await _read_json(request) or {}
    prompt = str(body.get("prompt", "")).strip()[:300]
    if not prompt:
        return JSONResponse({"error": "Describe the sound."}, status_code=400)
    try:
        duration = max(2.0, min(float(body.get("duration", 5) or 5), 30.0))
    except (TypeError, ValueError):
        duration = 5.0
    if not _capabilities_now().get("ace"):
        return JSONResponse(
            {"error": "The music generator is offline right now. "
                      "Nothing has been charged — please try again later."},
            status_code=503,
        )
    _refused = await _charge(user["email"], "sfx", duration)
    if _refused is not None:
        return _refused
    jid = uuid.uuid4().hex
    _sfx_jobs[jid] = {"status": "queued", "step": "Queued", "progress": 0,
                      "owner": user["email"],
                      "charged": entitlements.op_cost("sfx", duration)}
    asyncio.create_task(run_in_threadpool(_run_sfx, jid, prompt, duration))
    return JSONResponse({"id": jid})


async def sfx_status(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _sfx_jobs.get(request.path_params["jid"])
    if not j or j.get("owner") != user["email"]:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({k: v for k, v in j.items() if k not in ("out", "owner")})


async def sfx_file(request: Request) -> Response:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _sfx_jobs.get(request.path_params["jid"])
    if not j or j.get("owner") != user["email"] or j.get("status") != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    return FileResponse(j["out"], media_type="audio/mpeg", filename="sound-effect.mp3")


# --- Long-form Studio / Audiobooks (chunk long text -> stitched audio) ----- #
BOOK_DIR = Path(__file__).parent / "audiobooks"
_book_jobs: dict = {}


def _split_chunks(text: str, maxlen: int = 350) -> list[str]:
    """Split long text into sentence-aligned chunks the TTS can handle."""
    import re as _re
    text = _re.sub(r"\n{2,}", "\n\n", text.strip())
    sents = _re.split(r"(?<=[.!?।])\s+|\n+", text)
    chunks, cur = [], ""
    for s in sents:
        s = s.strip()
        if not s:
            continue
        if len(cur) + len(s) + 1 > maxlen and cur:
            chunks.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        chunks.append(cur)
    return chunks


def _run_audiobook(jid: str, text: str, voice: str, gap_ms: int) -> None:
    import tempfile as _tf
    try:
        _book_jobs[jid].update(status="processing", step="Preparing", progress=5)
        chunks = _split_chunks(text)
        if not chunks:
            raise RuntimeError("no text")
        BOOK_DIR.mkdir(exist_ok=True)
        is_hi = hinglish.is_hindi_voice(voice)
        parts = []
        silence = str(BOOK_DIR / f"{jid}_sil.wav")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-t", str(max(0.1, gap_ms / 1000)),
                        "-i", "anullsrc=r=44100:cl=stereo", silence], capture_output=True)
        for i, ch in enumerate(chunks):
            _book_jobs[jid].update(
                step=f"Narrating {i + 1}/{len(chunks)}",
                progress=5 + int(85 * i / len(chunks)))
            t = normalize_speech_text(ch)
            if is_hi:
                t = hinglish.to_devanagari(t)
            wavb, _m = ENGINE.synthesize(
                text=t, voice_id=voice, rate=1.0, pitch=1.0, volume=1.0, fmt="wav")
            p = str(BOOK_DIR / f"{jid}_p{i}.wav")
            with open(p, "wb") as f:
                f.write(wavb)
            parts.append(p)
        # concat parts with silence between
        _book_jobs[jid].update(step="Assembling", progress=92)
        listf = str(BOOK_DIR / f"{jid}_list.txt")
        with open(listf, "w") as f:
            for i, p in enumerate(parts):
                f.write(f"file '{p}'\n")
                if i < len(parts) - 1:
                    f.write(f"file '{silence}'\n")
        out = str(BOOK_DIR / f"{jid}.mp3")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
                        "-ar", "44100", "-b:a", "192k", out], capture_output=True)
        _book_jobs[jid].update(status="done", step="Completed", progress=100,
                               out=out, chunks=len(chunks))
        for p in parts + [silence, listf]:
            try:
                os.unlink(p)
            except OSError:
                pass
    except Exception as e:
        print(f"[audiobook] {jid} failed: {e!r}")
        _book_jobs[jid].update(status="failed", step="Failed", error=repr(e)[:200])


async def audiobook_create(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    body = await _read_json(request) or {}
    text = str(body.get("text", "")).strip()[:200000]
    if len(text) < 20:
        return JSONResponse({"error": "Add more text."}, status_code=400)
    voice = str(body.get("voice", "af_heart")).strip()
    try:
        gap_ms = max(0, min(int(body.get("gap_ms", 400)), 2000))
    except (TypeError, ValueError):
        gap_ms = 400
    jid = uuid.uuid4().hex
    _book_jobs[jid] = {"status": "queued", "step": "Queued", "progress": 0,
                       "owner": user["email"]}
    asyncio.create_task(run_in_threadpool(_run_audiobook, jid, text, voice, gap_ms))
    return JSONResponse({"id": jid})


async def audiobook_status(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _book_jobs.get(request.path_params["jid"])
    if not j or j.get("owner") != user["email"]:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({k: v for k, v in j.items() if k not in ("out", "owner")})


async def audiobook_file(request: Request) -> Response:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _book_jobs.get(request.path_params["jid"])
    if not j or j.get("owner") != user["email"] or j.get("status") != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    return FileResponse(j["out"], media_type="audio/mpeg", filename="audiobook.mp3")


# --- Audio Native (embeddable "Listen to this article" player) ------------- #
AN_DIR = Path(__file__).parent / "audionative"
_an_jobs: dict = {}


def _run_audionative(aid: str, text: str, voice: str, title: str, owner: str) -> None:
    import tempfile as _tf
    try:
        _an_jobs[aid].update(status="processing", step="Narrating", progress=10)
        chunks = _split_chunks(text)
        if not chunks:
            raise RuntimeError("no text")
        AN_DIR.mkdir(exist_ok=True)
        is_hi = hinglish.is_hindi_voice(voice) or voice.startswith("if5")
        parts = []
        sil = str(AN_DIR / f"{aid}_sil.wav")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-t", "0.35",
                        "-i", "anullsrc=r=44100:cl=stereo", sil], capture_output=True)
        for i, ch in enumerate(chunks):
            _an_jobs[aid].update(progress=10 + int(80 * i / len(chunks)))
            t = normalize_speech_text(ch)
            if is_hi:
                t = hinglish.to_devanagari(t)
            if voice.startswith("if5-"):
                ref = _if5_ref(voice)
                wavb, _m = if5_synth(t, ref[0], ref[1], fmt="wav") if ref else (b"", "")
            else:
                wavb, _m = ENGINE.synthesize(text=t, voice_id=voice, rate=1.0,
                                             pitch=1.0, volume=1.0, fmt="wav")
            p = str(AN_DIR / f"{aid}_p{i}.wav")
            with open(p, "wb") as f:
                f.write(wavb)
            parts.append(p)
        listf = str(AN_DIR / f"{aid}_list.txt")
        with open(listf, "w") as f:
            for i, p in enumerate(parts):
                f.write(f"file '{p}'\n")
                if i < len(parts) - 1:
                    f.write(f"file '{sil}'\n")
        out = str(AN_DIR / f"{aid}.mp3")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
                        "-ar", "44100", "-b:a", "192k", out], capture_output=True)
        with open(AN_DIR / f"{aid}.json", "w") as f:
            json.dump({"title": title, "voice": voice, "owner": owner}, f)
        for p in parts + [sil, listf]:
            try:
                os.unlink(p)
            except OSError:
                pass
        _an_jobs[aid].update(status="done", step="Completed", progress=100)
    except Exception as e:
        print(f"[audionative] {aid} failed: {e!r}")
        _an_jobs[aid].update(status="failed", step="Failed", error=repr(e)[:200])


async def audionative_create(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    body = await _read_json(request) or {}
    text = str(body.get("text", "")).strip()[:50000]
    if len(text) < 20:
        return JSONResponse({"error": "Add more text."}, status_code=400)
    title = (str(body.get("title", "")).strip() or "Listen to this article")[:120]
    voice = str(body.get("voice", "af_heart")).strip()
    aid = uuid.uuid4().hex
    _an_jobs[aid] = {"status": "queued", "step": "Queued", "progress": 0,
                     "owner": user["email"], "title": title}
    asyncio.create_task(run_in_threadpool(
        _run_audionative, aid, text, voice, title, user["email"]))
    host = request.headers.get("host", "prapthi.ai")
    return JSONResponse({"id": aid, "embed_url": f"https://{host}/api/embed/{aid}"})


async def audionative_status(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _an_jobs.get(request.path_params["aid"])
    # also report done if the file exists (survives restarts)
    aid = request.path_params["aid"]
    if (AN_DIR / f"{aid}.mp3").exists():
        host = request.headers.get("host", "prapthi.ai")
        return JSONResponse({"status": "done", "progress": 100,
                             "embed_url": f"https://{host}/api/embed/{aid}"})
    if not j or j.get("owner") != user["email"]:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({k: v for k, v in j.items() if k != "owner"})


# Public (no-auth) embed endpoints — loaded on third-party sites.
_EMBED_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>html,body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.w{{display:flex;align-items:center;gap:12px;padding:10px 14px;border:1px solid #e6e6e9;
border-radius:14px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.b{{width:40px;height:40px;border:0;border-radius:50%;background:#6d28d9;color:#fff;
font-size:16px;cursor:pointer;flex:0 0 auto}}.t{{font-weight:600;font-size:14px;color:#111}}
.s{{width:100%;accent-color:#6d28d9}} .m{{font-size:11px;color:#9aa}} a{{color:#9aa;text-decoration:none;font-size:10px}}</style></head>
<body><div class="w"><button class="b" id="pp">▶</button>
<div style="flex:1;min-width:0"><div class="t">{title}</div>
<input class="s" id="sk" type="range" min="0" max="100" value="0"></div>
<span class="m" id="tm">0:00</span><a href="https://prapthi.ai" target="_blank">▮ Prapthi</a>
<audio id="au" src="{audio}" preload="none"></audio></div>
<script>
var a=document.getElementById('au'),b=document.getElementById('pp'),s=document.getElementById('sk'),t=document.getElementById('tm');
function fmt(x){{x=x||0;var m=Math.floor(x/60),c=Math.floor(x%60);return m+':'+(c<10?'0':'')+c}}
b.onclick=function(){{if(a.paused){{a.play();b.textContent='❚❚'}}else{{a.pause();b.textContent='▶'}}}};
a.ontimeupdate=function(){{if(a.duration){{s.value=100*a.currentTime/a.duration;t.textContent=fmt(a.currentTime)}}}};
a.onended=function(){{b.textContent='▶'}};
s.oninput=function(){{if(a.duration)a.currentTime=s.value*a.duration/100}};
</script></body></html>"""


async def embed_player(request: Request) -> Response:
    aid = request.path_params["aid"]
    meta_p = AN_DIR / f"{aid}.json"
    if not (AN_DIR / f"{aid}.mp3").exists():
        return Response("Not found", status_code=404)
    title = "Listen to this article"
    try:
        title = json.loads(meta_p.read_text()).get("title", title)
    except Exception:
        pass
    host = request.headers.get("host", "prapthi.ai")
    html = _EMBED_HTML.format(title=title, audio=f"https://{host}/api/embed/{aid}/audio")
    return Response(html, media_type="text/html",
                    headers={"X-Frame-Options": "ALLOWALL", "Access-Control-Allow-Origin": "*"})


async def embed_audio(request: Request) -> Response:
    aid = request.path_params["aid"]
    p = AN_DIR / f"{aid}.mp3"
    if not p.exists():
        return Response("Not found", status_code=404)
    return FileResponse(str(p), media_type="audio/mpeg",
                        headers={"Access-Control-Allow-Origin": "*"})


# --- Ads Engine (LLM writes the ad script -> voiced) ----------------------- #
ADS_DIR = Path(__file__).parent / "ads_out"
_ads_jobs: dict = {}
_ADS_LANG = {"en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu",
             "kn": "Kannada", "ml": "Malayalam", "bn": "Bengali", "mr": "Marathi",
             "gu": "Gujarati", "pa": "Punjabi"}


def _ads_synth(text: str, voice: str) -> bytes:
    if voice.startswith("if5-"):
        ref = _if5_ref(voice)
        if ref:
            a, _m = if5_synth(text, ref[0], ref[1], fmt="mp3")
            return a
    a, _m = ENGINE.synthesize(text=text, voice_id=voice, rate=1.0, pitch=1.0,
                              volume=1.0, fmt="mp3")
    return a


def _run_ads(aid: str, brief: str, lang: str, voice: str, tone: str, seconds: int) -> None:
    try:
        _ads_jobs[aid].update(status="processing", step="Writing script", progress=20)
        ln = _ADS_LANG.get(lang, "English")
        sysp = (f"You are an award-winning advertising copywriter. Write a punchy, "
                f"persuasive {seconds}-second voice ad in {ln}. Output ONLY the spoken "
                f"ad copy — no labels, no stage directions, no quotes, no emojis.")
        userp = f"Product/brief: {brief}\nTone: {tone}"
        script = _llm_chat([{"role": "system", "content": sysp},
                            {"role": "user", "content": userp}], max_tokens=320).strip()
        _ads_jobs[aid].update(step="Voicing", progress=70)
        t = script
        if hinglish.is_hindi_voice(voice) or voice.startswith("if5") or lang == "hi":
            t = hinglish.to_devanagari(t)
        audio = _ads_synth(t, voice)
        ADS_DIR.mkdir(exist_ok=True)
        with open(ADS_DIR / f"{aid}.mp3", "wb") as f:
            f.write(audio)
        _ads_jobs[aid].update(status="done", step="Completed", progress=100, script=script)
    except Exception as e:
        print(f"[ads] {aid} failed: {e!r}")
        _ads_jobs[aid].update(status="failed", step="Failed", error=repr(e)[:200])


async def ads_create(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    body = await _read_json(request) or {}
    brief = str(body.get("brief", "")).strip()[:1000]
    if len(brief) < 5:
        return JSONResponse({"error": "Describe what you're advertising."}, status_code=400)
    lang = str(body.get("language", "en")).lower()
    voice = str(body.get("voice", "af_heart")).strip()
    tone = str(body.get("tone", "energetic")).strip()[:40]
    try:
        seconds = max(10, min(int(body.get("seconds", 30)), 60))
    except (TypeError, ValueError):
        seconds = 30
    aid = uuid.uuid4().hex
    _ads_jobs[aid] = {"status": "queued", "step": "Queued", "progress": 0,
                      "owner": user["email"]}
    asyncio.create_task(run_in_threadpool(_run_ads, aid, brief, lang, voice, tone, seconds))
    return JSONResponse({"id": aid})


async def ads_status(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _ads_jobs.get(request.path_params["aid"])
    if not j or j.get("owner") != user["email"]:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({k: v for k, v in j.items() if k != "owner"})


async def ads_file(request: Request) -> Response:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _ads_jobs.get(request.path_params["aid"])
    if not j or j.get("owner") != user["email"] or j.get("status") != "done":
        return JSONResponse({"error": "not ready"}, status_code=404)
    return FileResponse(str(ADS_DIR / f"{request.path_params['aid']}.mp3"),
                        media_type="audio/mpeg", filename="ad.mp3")


# --- Voice Isolator (Demucs: split vocals / music / drums / bass / other) -- #
ISOLATE_DIR = Path(__file__).parent / "isolate"
_iso_jobs: dict = {}
_ISO_KINDS = ("vocals", "instrumental", "drums", "bass", "other")


def _run_isolate(jid: str, in_path: str) -> None:
    try:
        _iso_jobs[jid].update(status="processing", progress=25, step="Separating audio")
        wav = str(ISOLATE_DIR / f"{jid}_norm.wav")
        subprocess.run(["ffmpeg", "-y", "-i", in_path, "-ac", "2", "-ar", "44100", wav],
                       capture_output=True)
        songmod.acestep_stems(wav, str(ISOLATE_DIR), jid)  # writes jid_<kind>.mp3
        kinds = [k for k in _ISO_KINDS if (ISOLATE_DIR / f"{jid}_{k}.mp3").exists()]
        if not kinds:
            raise RuntimeError("separation produced no output")
        _iso_jobs[jid].update(status="done", progress=100, step="Completed", kinds=kinds)
    except Exception as e:
        print(f"[isolate] {jid} failed: {e!r}")
        _iso_jobs[jid].update(status="failed", step="Failed", error=repr(e)[:200])
    finally:
        for p in (in_path, str(ISOLATE_DIR / f"{jid}_norm.wav")):
            try:
                os.unlink(p)
            except OSError:
                pass


async def isolate_create(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"error": "No file uploaded."}, status_code=400)
    ext = os.path.splitext(getattr(upload, "filename", "") or "")[1].lower() or ".mp3"
    data = await upload.read()
    if len(data) > 100 * 1024 * 1024:
        return JSONResponse({"error": "File too large (max 100MB)."}, status_code=400)
    ISOLATE_DIR.mkdir(exist_ok=True)
    jid = uuid.uuid4().hex
    in_path = str(ISOLATE_DIR / f"{jid}_in{ext}")
    with open(in_path, "wb") as f:
        f.write(data)
    _iso_jobs[jid] = {"status": "queued", "step": "Queued", "progress": 0,
                      "owner": user["email"]}
    asyncio.create_task(run_in_threadpool(_run_isolate, jid, in_path))
    return JSONResponse({"id": jid})


async def isolate_status(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    j = _iso_jobs.get(request.path_params["jid"])
    if not j or j.get("owner") != user["email"]:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({k: v for k, v in j.items() if k != "owner"})


async def isolate_file(request: Request) -> Response:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    jid = request.path_params["jid"]
    kind = request.path_params["kind"]
    j = _iso_jobs.get(jid)
    if not j or j.get("owner") != user["email"] or kind not in _ISO_KINDS:
        return JSONResponse({"error": "not found"}, status_code=404)
    p = ISOLATE_DIR / f"{jid}_{kind}.mp3"
    if not p.exists():
        return JSONResponse({"error": "not ready"}, status_code=404)
    return FileResponse(str(p), media_type="audio/mpeg", filename=f"{kind}.mp3")


# --- Speech to Text (Whisper) --------------------------------------------- #
async def transcribe_audio(request: Request) -> JSONResponse:
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"error": "No file uploaded."}, status_code=400)
    ext = os.path.splitext(getattr(upload, "filename", "") or "")[1].lower() or ".mp3"
    data = await upload.read()
    if len(data) > 100 * 1024 * 1024:
        return JSONResponse({"error": "File too large (max 100MB)."}, status_code=400)
    import tempfile as _tf
    src = _tf.mktemp(suffix=ext)
    wav = _tf.mktemp(suffix=".wav")
    with open(src, "wb") as f:
        f.write(data)

    _refused = await _charge(user["email"], "stt", dubbing._dur(src))
    if _refused is not None:
        for _p in (src, wav):
            try:
                os.remove(_p)
            except OSError:
                pass
        return _refused

    def _work():
        dubbing.extract_audio(src, wav)
        return dubbing.transcribe(wav)

    try:
        segs, lang = await run_in_threadpool(_work)
    except Exception as e:
        return JSONResponse({"error": repr(e)[:200]}, status_code=500)
    finally:
        for p in (src, wav):
            try:
                os.unlink(p)
            except OSError:
                pass
    return JSONResponse({
        "language": lang,
        "text": " ".join(s["text"] for s in segs),
        "segments": segs,
    })



# Engines with no Latin script in their vocabulary: an English word left in
# Latin is unreadable to them, so it must be written in Devanagari first.
# Parler and Chatterbox are multilingual and read English themselves.
_DEVANAGARI_ONLY = ("hi_in-", "mms-hin", "svara-hi", "if5", "hf_", "hm_")


def _needs_english_in_devanagari(voice_id: str) -> bool:
    v = (voice_id or "").lower().replace("server:", "")
    return v.startswith(_DEVANAGARI_ONLY)


async def _synth(request: Request, *, preview: bool, demo: bool = False) -> Response:
    ip = _client_ip(request)
    if demo:
        # public demo: no login, but rate-limited + text-capped below
        if _rate_limited(ip):
            return JSONResponse({"error": "rate limited"}, status_code=429)
    else:
        _user = await _current_user(request)
        if not _user:
            return _unauthorized()
        if _rate_limited(ip):
            return JSONResponse({"error": "rate limited"}, status_code=429)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    voice_id = str(body.get("voiceId", "")).strip()
    if not voice_id:
        return JSONResponse({"error": "voiceId required"}, status_code=400)

    # Cloned voice? Resolve the user's sample + language (owner-scoped lookup).
    clone = None
    if5clone = None
    if voice_id.startswith("if5clone:"):
        if5clone = await db.get_clone(voice_id.split(":", 1)[1], _user["email"])
        if not if5clone:
            return JSONResponse({"error": "unknown voice"}, status_code=400)
    elif voice_id.startswith("clone:"):
        clone = await db.get_clone(voice_id.split(":", 1)[1], _user["email"])
        if not clone:
            return JSONResponse({"error": "unknown voice"}, status_code=400)

    # Entitlements: a lapsed or free account may not use the premium
    # engines. Checked before any work is done, and before anything is
    # charged against the allowance.
    if not demo and _user:
        _account = await db.get_account(_user["email"])
        if not entitlements.may_use_voice(_account, voice_id):
            return JSONResponse(
                {"error": entitlements.UPGRADE_VOICE, "code": "upgrade_required"},
                status_code=402,
            )

    if preview:
        if if5clone:
            lang, name = "hi", if5clone["name"]
        elif clone:
            lang, name = clone["lang"], clone["name"]
        else:
            meta = _VOICE_META.get(voice_id) or _EXTRA_VOICE_META.get(voice_id)
            lang, name = meta if meta else ("en", "this voice")
        tmpl = PREVIEW_TEMPLATES.get(lang, PREVIEW_TEMPLATES["en"])
        text = tmpl.format(n=name)
    else:
        text = str(body.get("text", ""))
        if demo:
            text = text[:300]
        if not text.strip():
            return JSONResponse({"error": "text required"}, status_code=400)
        if len(text) > CHAR_CAP:
            return JSONResponse(
                {"error": f"text exceeds {CHAR_CAP} chars"}, status_code=413
            )
        # The slow engines cannot finish a long passage before the proxy gives
        # up, which would charge the customer for nothing. Refuse up front.
        _voice_cap = entitlements.max_chars_for(voice_id, CHAR_CAP)
        if len(text) > _voice_cap:
            return JSONResponse(
                {"error": entitlements.too_long_message(
                    voice_id, _voice_cap, len(text)),
                 "code": "text_too_long_for_voice"},
                status_code=413,
            )
        # Signed-in synthesis is charged against the monthly character
        # allowance. The demo endpoint is free (already capped + rate limited).
        if not demo and _user and not _user.get("is_admin"):
            await db.reset_period_if_due(_user["email"])
            ok, remaining = await db.consume_chars(_user["email"], len(text))
            if not ok:
                return JSONResponse(
                    {"error": "You have used your monthly characters. "
                              "Upgrade your plan to carry on.",
                     "code": "quota_exceeded"},
                    status_code=402,
                )
        text = normalize_speech_text(text)
        # Hinglish: for Hindi voices, convert common romanized Hindi words to
        # Devanagari so they're pronounced natively (QA #3/#4, best-effort).
        # Sanskrit voices are excluded — the dictionary is Hindi-specific.
        if (
            hinglish.is_hindi_voice(voice_id) or voice_id.startswith("if5")
        ) and voice_id not in SANSKRIT_VOICES:
            text = hinglish.to_devanagari(
                text, speak_english=_needs_english_in_devanagari(voice_id))

    try:
        rate = float(body.get("rate", 1.0))
        pitch = float(body.get("pitch", 1.0))
        volume = float(body.get("volume", 1.0))
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "rate, pitch and volume must be numbers"}, status_code=400
        )
    # Unspecified means mp3: playback does not need a lossless file, and a
    # client that omits the field must never be refused for it.
    _asked_fmt = str(body.get("format", "")).lower()
    fmt = "wav" if _asked_fmt == "wav" else "mp3"
    # The plans sell WAV as a *download* format, so only an explicit request
    # for one is gated — never playback.
    if (_asked_fmt == "wav" and not demo and _user
            and not entitlements.may_use_format(
                await db.get_account(_user["email"]), "wav")):
        return JSONResponse(
            {"error": entitlements.UPGRADE_WAV, "code": "upgrade_required"},
            status_code=402,
        )

    # Optional emotion (only the Parler HD engine acts on it; others ignore it).
    emotion = emotion_mod.normalize(str(body.get("emotion", "neutral")))
    # Emotion intensity (0 = subtle/none, 1 = normal, 2 = dramatic).
    try:
        intensity = float(body.get("intensity", 1.0))
    except (TypeError, ValueError):
        intensity = 1.0
    intensity = max(0.0, min(2.0, intensity))

    # Fold emotion (+ non-default intensity) into the cache key so each variant
    # caches separately, while keeping the neutral key identical to before.
    cache_vid = voice_id
    if emotion != "neutral":
        cache_vid = f"{voice_id}@{emotion}"
        if abs(intensity - 1.0) > 1e-3:
            cache_vid += f"#{intensity:.2f}"

    # Emotion prosody: scale the user's sliders by the emotion's feel factors
    # (themselves scaled by intensity) so happy is brighter/faster, sad
    # slower/softer, etc. — on every engine.
    def _prosody(emo: str) -> tuple[float, float, float]:
        es, ep, ev = _EMOTION_PROSODY.get(emo, (1.0, 1.0, 1.0))
        es = 1.0 + (es - 1.0) * intensity
        ep = 1.0 + (ep - 1.0) * intensity
        ev = 1.0 + (ev - 1.0) * intensity
        # Cap effective speed at 1.6× — beyond that, voices clip word endings (QA #2).
        return min(rate * es, 1.6), pitch * ep, volume * ev

    # "auto": follow the scenario sentence by sentence (emotion.detect).
    # One feeling throughout -> the normal single-shot path with that feeling.
    # Chants are never split: metre detection needs the whole verse.
    runs = (emotion_mod.detect(text)
            if emotion == "auto" and voice_id != "vagdhenu-sa-chant" else [])
    if emotion == "auto":
        emotion = runs[0][1] if len(runs) == 1 else ("neutral" if not runs else emotion)
    eng_rate, eng_pitch, eng_volume = _prosody(emotion if emotion != "auto" else "neutral")

    # Vāgdhenu renders per-meter, so the meter is part of the cache identity.
    if voice_id == "vagdhenu-sa-chant":
        _meter = str(body.get("meter", "auto")).strip() or "auto"
        cache_vid = f"{cache_vid}~{_meter}"

    def _cbx_ex(emo: str) -> tuple[float, float]:
        ex, cfg = emotion_mod.feel(emo).cbx
        return (max(0.25, min(2.0, 0.5 + (ex - 0.5) * intensity)), cfg)

    async def _render(t_: str, emo_: str, r_: float, p_: float, v_: float,
                      fmt_: str):
        """Run the right engine for this voice (one feeling, one chunk)."""
        if voice_id == "vagdhenu-sa-chant":
            meter = str(body.get("meter", "auto")).strip() or "auto"
            return await run_in_threadpool(
                vagdhenu_synth, t_,
                meter=meter, fmt=fmt_,
                speed=r_, pitch=p_, volume=v_,
            )
        elif if5clone:
            _rt = ""
            try:
                _rt = Path(if5clone["path"]).with_suffix(".txt").read_text().strip()
            except OSError:
                pass
            return await run_in_threadpool(
                if5_synth, t_, if5clone["path"], _rt,
                fmt=fmt_, speed=r_, pitch=p_, volume=v_,
            )
        elif voice_id.startswith("if5-"):
            ref = _if5_ref(voice_id)
            if not ref:
                raise EngineError("unknown voice")
            return await run_in_threadpool(
                if5_synth, t_, ref[0], ref[1],
                fmt=fmt_, speed=r_, pitch=p_, volume=v_,
            )
        elif clone:
            return await run_in_threadpool(
                chatterbox_synth,
                t_,
                language_id=clone["lang"],
                emotion=emo_,
                exaggeration=_cbx_ex(emo_),
                fmt=fmt_,
                audio_prompt_path=clone["path"],
                speed=r_,
                pitch=p_,
                volume=v_,
            )
        else:
            owner, vlang = _voice_owner(voice_id)
            native = owner in _NATIVE_EMOTION_ENGINES
            if native or emo_ in ("neutral", "auto"):
                return await run_in_threadpool(
                    ENGINE.synthesize,
                    text=t_,
                    voice_id=voice_id,
                    rate=r_,
                    pitch=p_,
                    volume=v_,
                    fmt=fmt_,
                    emotion=emo_,
                )
            # This engine cannot act. Render it plainly (user sliders only, no
            # emotion prosody) and reshape the melody, tempo and loudness for
            # the feeling — works in every language and keeps the voice.
            wav, _m = await run_in_threadpool(
                ENGINE.synthesize,
                text=t_,
                voice_id=voice_id,
                rate=rate,
                pitch=pitch,
                volume=volume,
                fmt="wav",
                emotion=emo_,
            )
            shaped = await run_in_threadpool(
                _tone_shape, wav, emo_, intensity, vlang
            )
            if shaped is None:  # shaping unavailable -> previous behaviour
                return await run_in_threadpool(
                    ENGINE.synthesize,
                    text=t_,
                    voice_id=voice_id,
                    rate=r_,
                    pitch=p_,
                    volume=v_,
                    fmt=fmt_,
                    emotion=emo_,
                )
            if fmt_ == "wav":
                return shaped, "audio/wav"
            return await run_in_threadpool(_wav_to_mp3, shaped)

    async def _render_scenario(runs_):
        """auto mode: each run in its own feeling, joined with short pauses."""
        import io as _io
        import numpy as _np
        import soundfile as _sf
        pieces, sr = [], None
        for t_, emo_ in runs_:
            r_, p_, v_ = _prosody(emo_)
            wav, _m = await _render(t_, emo_, r_, p_, v_, "wav")
            y, s_ = _sf.read(_io.BytesIO(wav), dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = y.mean(axis=1)
            if sr is None:
                sr = s_
            elif s_ != sr:
                import librosa as _lr
                y = _lr.resample(y, orig_sr=s_, target_sr=sr)
            if pieces:
                pieces.append(_np.zeros(int(sr * 0.28), dtype=_np.float32))
            pieces.append(y)
        buf = _io.BytesIO()
        _sf.write(buf, _np.concatenate(pieces), sr, format="WAV", subtype="PCM_16")
        if fmt == "wav":
            return buf.getvalue(), "audio/wav"
        return await run_in_threadpool(_wav_to_mp3, buf.getvalue())

    args = (cache_vid, text, rate, pitch, volume, fmt)

    # Fast path: serve an identical past result instantly (huge win for Parler).
    hit = cache.get(*args)
    if hit:
        audio, mime = hit
        return Response(audio, media_type=mime, headers=_audio_headers("HIT"))

    # Slow path: synthesize. Reject when the queue is already full so a flood of
    # slow requests can't pile up unbounded.
    global _synth_waiting
    if _synth_waiting >= _MAX_QUEUE:
        return JSONResponse(
            {"error": "server busy, please try again shortly"}, status_code=503
        )
    _synth_waiting += 1
    try:
        # Lock serializes torch use; threadpool keeps the event loop free.
        # Re-check the cache inside the lock in case a concurrent request just
        # produced the same audio.
        async with _synth_lock:
            hit = cache.get(*args)
            if hit:
                audio, mime = hit
                return Response(
                    audio, media_type=mime, headers=_audio_headers("HIT")
                )
            try:
                if len(runs) > 1:
                    audio, mime = await _render_scenario(runs)
                else:
                    audio, mime = await _render(
                        text, emotion, eng_rate, eng_pitch, eng_volume, fmt)
            except EngineError as e:
                return JSONResponse({"error": str(e)}, status_code=500)
            except Exception as e:  # pragma: no cover - defensive
                # Log detail server-side; return a generic message so internal
                # paths / stack details aren't disclosed to clients.
                print(f"[voxforge] synthesis error: {e!r}")
                return JSONResponse(
                    {"error": "synthesis failed, please try again"},
                    status_code=500,
                )
            cache.put(*args, audio, mime)
    finally:
        _synth_waiting -= 1

    return Response(audio, media_type=mime, headers=_audio_headers("MISS"))


# Engines whose model really acts emotions; everything else gets its melody
# reshaped instead (measured: reshaping moves pitch spread by 2-3 semitones,
# the old flat pitch shift moved it by ~0).
_NATIVE_EMOTION_ENGINES = {"SvaraEngine", "ChatterboxEngine"}
_VOICE_OWNER: dict[str, tuple[str, str]] = {}


def _voice_owner(voice_id: str) -> tuple[str, str]:
    """(engine class name, language) for a library voice."""
    if voice_id not in _VOICE_OWNER:
        try:
            langs = {v.id: v.lang for v in ENGINE.list_voices()}
            for vid, eng in getattr(ENGINE, "_owner", {}).items():
                _VOICE_OWNER[vid] = (type(eng).__name__, langs.get(vid, "en"))
        except Exception as e:  # pragma: no cover - never break synthesis
            print(f"[voxforge] voice owner map failed: {e!r}")
    return _VOICE_OWNER.get(voice_id, ("", "en"))


def _tone_shape(wav: bytes, emotion: str, intensity: float, lang: str) -> bytes | None:
    """Reshape a WAV for `emotion`; None when shaping did not apply."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        path = tf.name
        tf.write(wav)
    try:
        if not expressive_dsp.shape(path, emotion, intensity, lang):
            return None
        with open(path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _wav_to_mp3(wav: bytes) -> tuple[bytes, str]:
    import subprocess as _sp
    proc = _sp.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "wav",
                    "-i", "pipe:0", "-codec:a", "libmp3lame", "-b:a", "128k",
                    "-f", "mp3", "pipe:1"], input=wav, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        raise EngineError("mp3 encode failed")
    return proc.stdout, "audio/mpeg"


def _audio_headers(cache_status: str) -> dict:
    # Audio may be cached on disk server-side, but never persist user text;
    # the browser shouldn't cache the response either.
    return {"Cache-Control": "no-store", "X-Cache": cache_status}


async def synthesize(request: Request) -> Response:
    return await _synth(request, preview=False)



# --- admin ---------------------------------------------------------------- #
async def admin_stats_route(request: Request) -> JSONResponse:
    """Owner-only dashboard data. Refuses anyone who is not an admin, and says
    nothing useful to them — an ordinary user must not learn this exists."""
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    if not user.get("is_admin"):
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(await db.admin_stats())


# --- billing -------------------------------------------------------------- #
async def billing_plans(request: Request) -> JSONResponse:
    """Plans, whether payments are live, and the caller's own account."""
    account = None
    user = await _current_user(request)
    if user:
        await db.reset_period_if_due(user["email"])
        account = await db.get_account(user["email"])
        if account:
            if entitlements.effective_plan(account) == "owner":
                # The owner is not on a plan and has no allowance to spend.
                account = {"plan": "owner", "chars_allowance": None,
                           "chars_used": 0, "expires_at": None}
            else:
                account = {
                    "plan": "free" if account["expired"] else account["plan"],
                    "chars_allowance": 12000 if account["expired"] else account["chars_allowance"],
                    "chars_used": account["chars_used"],
                    "expires_at": account["plan_expires_at"].isoformat()
                    if account["plan_expires_at"] else None,
                }
    return JSONResponse({
        "plans": billing.public_plans(),
        "enabled": billing.enabled(),
        "account": account,
    })


async def billing_order(request: Request) -> JSONResponse:
    """Start a payment. The price is read from the server's plan table."""
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    if not billing.enabled():
        return JSONResponse({"error": "Payments are not switched on yet."}, status_code=503)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    try:
        order = await run_in_threadpool(
            billing.create_order, str(body.get("plan", "")), user["email"])
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        print(f"[billing] order failed: {e!r}")
        return JSONResponse({"error": "Could not start payment. Please try again."},
                            status_code=502)
    return JSONResponse(order)


async def billing_verify(request: Request) -> JSONResponse:
    """Grant the plan only if Razorpay's signature checks out server-side."""
    user = await _current_user(request)
    if not user:
        return _unauthorized()
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    order_id = str(body.get("razorpay_order_id", ""))
    payment_id = str(body.get("razorpay_payment_id", ""))
    signature = str(body.get("razorpay_signature", ""))
    if not billing.verify_payment(order_id, payment_id, signature):
        return JSONResponse({"error": "Payment could not be verified."}, status_code=400)

    order = await run_in_threadpool(billing.fetch_order, order_id)
    plan_id = (order or {}).get("notes", {}).get("plan", "")
    plan = billing.PLANS.get(plan_id)
    if not plan:
        return JSONResponse({"error": "Unknown plan on that order."}, status_code=400)

    await db.mark_paid(payment_id, order_id, user["email"], plan_id,
                       plan["price"] * 100, "callback", plan["chars"],
                       billing.PLAN_DAYS)
    account = await db.get_account(user["email"])
    return JSONResponse({"ok": True, "account": {
        "plan": account["plan"], "chars_allowance": account["chars_allowance"],
        "chars_used": account["chars_used"],
        "expires_at": account["plan_expires_at"].isoformat()
        if account["plan_expires_at"] else None}})


async def billing_webhook(request: Request) -> JSONResponse:
    """Razorpay's own confirmation — authoritative, since a browser callback
    can be lost. Signed over the raw body, so read bytes before parsing."""
    raw = await request.body()
    sig = request.headers.get("x-razorpay-signature", "")
    if not billing.verify_webhook(raw, sig):
        return JSONResponse({"error": "bad signature"}, status_code=400)
    try:
        event = json.loads(raw)
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    if event.get("event") not in ("payment.captured", "order.paid"):
        return JSONResponse({"ok": True, "ignored": True})

    pay = (event.get("payload", {}).get("payment", {}).get("entity", {}))
    payment_id, order_id = pay.get("id", ""), pay.get("order_id", "")
    notes = pay.get("notes") or {}
    plan_id = notes.get("plan", "")
    email = notes.get("email", "")
    if not (payment_id and order_id and plan_id and email):
        order = await run_in_threadpool(billing.fetch_order, order_id)
        notes = (order or {}).get("notes", {})
        plan_id = plan_id or notes.get("plan", "")
        email = email or notes.get("email", "")
    plan = billing.PLANS.get(plan_id)
    if not (plan and email):
        return JSONResponse({"ok": True, "ignored": True})

    granted = await db.mark_paid(payment_id, order_id, email, plan_id,
                                 plan["price"] * 100, "webhook", plan["chars"],
                                 billing.PLAN_DAYS)
    print(f"[billing] webhook {payment_id} plan={plan_id} granted={granted}")
    return JSONResponse({"ok": True})


# --- Studio capabilities -------------------------------------------------
# The dashboard asks which studios can run right now and greys out the rest,
# so users see "coming soon" instead of a tool that errors when used.
_CAPS_CACHE: dict = {"t": 0.0, "v": None}


def _probe_http(url: str) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _capabilities_now() -> dict:
    import importlib.util
    import shutil as _sh
    stt = importlib.util.find_spec("faster_whisper") is not None
    llm = _probe_http(os.environ.get("LLM_URL", "http://127.0.0.1:8005"))
    ace = _probe_http(os.environ.get("ACESTEP_URL", "http://127.0.0.1:8003"))
    sargam_ok = bool(_sh.which("fluidsynth")) and os.path.exists(sargam.SOUNDFONT)
    return {"stt": stt, "llm": llm, "agent": stt and llm, "ace": ace, "sargam": sargam_ok}


async def capabilities(request: Request) -> Response:
    import time as _t
    now = _t.time()
    if _CAPS_CACHE["v"] is None or now - _CAPS_CACHE["t"] > 30:
        _CAPS_CACHE["v"] = await run_in_threadpool(_capabilities_now)
        _CAPS_CACHE["t"] = now
    return JSONResponse(_CAPS_CACHE["v"])


async def demo_synthesize(request: Request) -> Response:
    # public: homepage "Try the generator" — no login, capped + rate-limited
    return await _synth(request, preview=False, demo=True)


async def preview(request: Request) -> Response:
    return await _synth(request, preview=True)


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/capabilities", capabilities, methods=["GET"]),
    Route("/admin/stats", admin_stats_route, methods=["GET"]),
    Route("/billing/plans", billing_plans, methods=["GET"]),
    Route("/billing/order", billing_order, methods=["POST"]),
    Route("/billing/verify", billing_verify, methods=["POST"]),
    Route("/billing/webhook", billing_webhook, methods=["POST"]),
    Route("/auth/signup", signup, methods=["POST"]),
    Route("/auth/verify", verify_email, methods=["POST"]),
    Route("/auth/resend", resend_code, methods=["POST"]),
    Route("/auth/login", login, methods=["POST"]),
    Route("/auth/logout", logout, methods=["POST"]),
    Route("/auth/me", me, methods=["GET"]),
    Route("/auth/forgot", forgot_password, methods=["POST"]),
    Route("/auth/reset", reset_password, methods=["POST"]),
    Route("/voices", voices, methods=["GET"]),
    Route("/voices/clone", clone_create, methods=["POST"]),
    Route("/voices/clone-if5", if5_clone_create, methods=["POST"]),
    # The dashboard (lib/clone.ts) posts Indic clones here.
    Route("/voices/clone-hd", if5_clone_create, methods=["POST"]),
    Route("/voices/clone/{vid}", clone_delete, methods=["DELETE"]),
    Route("/song/extract", song_extract, methods=["POST"]),
    Route("/song/analyze", song_analyze, methods=["POST"]),
    Route("/song/create", song_create, methods=["POST"]),
    Route("/song/list", song_list, methods=["GET"]),
    Route("/song/{sid}/regenerate", song_regenerate, methods=["POST"]),
    Route("/song/{sid}/stems", song_stems, methods=["POST"]),
    Route("/song/{sid}/stem/{kind}", song_stem_file, methods=["GET"]),
    Route("/melody/summary", melody_summary, methods=["POST"]),
    Route("/melody/render", melody_render, methods=["POST"]),
    Route("/dub", dub_create, methods=["POST"]),
    Route("/dub/{jid}", dub_status, methods=["GET"]),
    Route("/dub/{jid}/file", dub_file, methods=["GET"]),
    Route("/isolate", isolate_create, methods=["POST"]),
    Route("/isolate/{jid}", isolate_status, methods=["GET"]),
    Route("/isolate/{jid}/file/{kind}", isolate_file, methods=["GET"]),
    Route("/transcribe", transcribe_audio, methods=["POST"]),
    Route("/agent/chat", agent_chat, methods=["POST"]),
    Route("/agent/voice", agent_voice, methods=["POST"]),
    Route("/audiobook", audiobook_create, methods=["POST"]),
    Route("/audiobook/{jid}", audiobook_status, methods=["GET"]),
    Route("/audiobook/{jid}/file", audiobook_file, methods=["GET"]),
    Route("/audionative", audionative_create, methods=["POST"]),
    Route("/audionative/{aid}", audionative_status, methods=["GET"]),
    Route("/embed/{aid}", embed_player, methods=["GET"]),
    Route("/embed/{aid}/audio", embed_audio, methods=["GET"]),
    Route("/ads", ads_create, methods=["POST"]),
    Route("/ads/{aid}", ads_status, methods=["GET"]),
    Route("/ads/{aid}/file", ads_file, methods=["GET"]),
    Route("/sfx", sfx_create, methods=["POST"]),
    Route("/sfx/{jid}", sfx_status, methods=["GET"]),
    Route("/sfx/{jid}/file", sfx_file, methods=["GET"]),
    Route("/song/{sid}/audio", song_audio, methods=["GET"]),
    Route("/song/{sid}", song_status, methods=["GET"]),
    Route("/song/{sid}", song_delete, methods=["DELETE"]),
    Route("/synthesize", synthesize, methods=["POST"]),
    Route("/demo/synthesize", demo_synthesize, methods=["POST"]),
    Route("/preview", preview, methods=["POST"]),
]

MAX_BODY = int(os.environ.get("VOXFORGE_MAX_BODY", str(1024 * 1024)))  # 1 MB
MAX_CLONE_BODY = int(
    os.environ.get("VOXFORGE_MAX_CLONE_BODY", str(12 * 1024 * 1024))
)  # 12 MB for voice-clone audio uploads
# Voice cloning: language ids accepted (Chatterbox multilingual) + storage dir.
_CLONE_LANGS = {
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja",
    "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
}
_MAX_CLONES_PER_USER = int(os.environ.get("VOXFORGE_MAX_CLONES", "10"))
# Set during start-up; background threads use it to reach the database.
_LOOP = None
CLONE_DIR = Path(__file__).parent / "voices_clone"

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    # API returns only JSON/audio — lock the response down to nothing else.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies (memory-DoS guard) and add hardening
    headers to every response."""

    async def dispatch(self, request: Request, call_next):
        # Voice-clone uploads carry an audio sample, so allow a larger body there.
        limit = (
            MAX_CLONE_BODY
            if request.url.path in ("/voices/clone", "/voices/clone-if5",
                                     "/voices/clone-hd", "/song/extract")
            else MAX_BODY
        )
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > limit:
            return JSONResponse({"error": "request too large"}, status_code=413)
        resp = await call_next(request)
        for k, v in _SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        return resp


# CORS: a wildcard origin can NOT be safely combined with credentials, so when
# ALLOWED_ORIGIN is "*" we disable credentialed CORS (the SameSite=Strict
# session cookie already blocks cross-site auth). Set ALLOWED_ORIGIN to your
# real origin(s) in production to allow credentialed cross-origin use.
if ALLOWED_ORIGIN == "*":
    _cors = dict(allow_origins=["*"], allow_credentials=False)
else:
    _cors = dict(
        allow_origins=[o.strip() for o in ALLOWED_ORIGIN.split(",") if o.strip()],
        allow_credentials=True,
    )

middleware = [
    Middleware(SecurityMiddleware),
    Middleware(
        CORSMiddleware,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        **_cors,
    ),
]


async def _seed_master() -> None:
    """Create a verified admin account on first run if it doesn't exist."""
    email = os.environ.get("VOXFORGE_MASTER_USER", "admin@ayaanvoice.local").lower()
    if await db.get_user(email):
        return
    pw = os.environ.get("VOXFORGE_MASTER_PASSWORD") or auth.gen_password()
    await db.create_user(email, auth.hash_record(pw), is_admin=True)
    await db.mark_verified(email)
    try:
        from pathlib import Path

        p = Path(__file__).parent / "MASTER_CREDENTIALS.txt"
        p.write_text(f"Prapthi Ai — master admin\nemail: {email}\npassword: {pw}\n")
        os.chmod(p, 0o600)
    except OSError:
        pass
    print(f"[voxforge][auth] master admin created: {email} "
          "(password in MASTER_CREDENTIALS.txt)")


@contextlib.asynccontextmanager
async def lifespan(_app):
    global _LOOP
    _LOOP = asyncio.get_running_loop()
    await db.init_db()
    await _seed_master()
    yield
    await db.close_db()


app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
