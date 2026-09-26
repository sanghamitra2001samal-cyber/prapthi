"""What each plan is actually allowed to do.

The pricing page promises three things a server can enforce: which voices you
may use, how many voices you may clone, and which download formats you get.
Everything here mirrors that page, so a customer is never sold something the
backend refuses — or handed something they did not pay for.

The free/premium split follows real cost. Piper, Kokoro and MMS render a
sentence in about 1.5-2 seconds and carry the free tier across 45 languages.
Chatterbox, Parler, svara and Vāgdhenu take 9-45 seconds of CPU for the same
sentence (measured), so they sit behind a paid plan, along with voice cloning
which runs on the same expensive path.

An expired paid plan is treated exactly as free — entitlements must never
outlive the payment.
"""
from __future__ import annotations

# Voice ids belonging to the slow, expensive engines. Cloned voices are
# premium too: they are rendered by Chatterbox/IndicF5.
PREMIUM_PREFIXES = (
    "chatterbox-",
    "parler-",
    "svara-",
    "vagdhenu",
    "if5",          # covers if5-* voices and if5clone:*
    "clone:",
)

FEATURES: dict[str, dict] = {
    "free":  {"premium_voices": False, "clones": 0,  "wav": False},
    "mid":   {"premium_voices": True,  "clones": 3,  "wav": True},
    "elite": {"premium_voices": True,  "clones": 10, "wav": True},
}


def is_premium_voice(voice_id: str) -> bool:
    """True for voices that only a paid plan may use."""
    vid = (voice_id or "").lower()
    return vid.startswith(PREMIUM_PREFIXES)


def effective_plan(account: dict | None) -> str:
    """The plan we will actually honour. Unknown or lapsed plans read as free."""
    if not account:
        return "free"
    if account.get("expired"):
        return "free"
    plan = str(account.get("plan") or "free").lower()
    return plan if plan in FEATURES else "free"


def features(account: dict | None) -> dict:
    return FEATURES[effective_plan(account)]


def clone_limit(account: dict | None) -> int:
    return features(account)["clones"]


def may_use_voice(account: dict | None, voice_id: str) -> bool:
    return not is_premium_voice(voice_id) or features(account)["premium_voices"]


def may_use_format(account: dict | None, fmt: str) -> bool:
    return fmt != "wav" or features(account)["wav"]


# --- messages shown to the customer -------------------------------------- #
UPGRADE_VOICE = ("This voice is part of the paid plans. Upgrade to Mid or "
                 "Elite to use every premium voice.")
UPGRADE_WAV = ("WAV downloads are part of the paid plans. MP3 is available on "
               "every plan, or upgrade for WAV.")
UPGRADE_CLONE_FREE = ("Voice cloning is part of the paid plans. Upgrade to Mid "
                      "for 3 cloned voices, or Elite for 10.")


def clone_limit_message(plan: str, limit: int) -> str:
    if limit == 0:
        return UPGRADE_CLONE_FREE
    if plan == "mid":
        return (f"You have used all {limit} cloned voices on Mid. Upgrade to "
                f"Elite for 10, or delete one to make room.")
    return (f"You have used all {limit} cloned voices. Delete one to make room.")


# --- what the extras cost, in characters of allowance -------------------- #
# Derived from measurement on this CPU-only box, not guessed:
#   * one character of TTS costs ~3.5 ms of compute (fast Piper voice)
#   * transcription runs at 1.4x realtime = ~729 ms per second of audio,
#     i.e. ~209 characters' worth for every second transcribed
#   * dubbing = transcribe + translate + re-speak the whole script, so it is
#     strictly more expensive than transcription alone
# Songs and sound effects run on ACE-Step, which is currently offline and could
# not be measured; those two figures are carried over from the earlier credit
# design and are marked as estimates.
#
# Every value can be overridden without a deploy, e.g. PRAPTHI_COST_STT_SEC=80.
import os as _os

OP_COSTS = {
    # per second of audio submitted
    "stt": float(_os.environ.get("PRAPTHI_COST_STT_SEC", "150")),
    # per second of video submitted
    "dub": float(_os.environ.get("PRAPTHI_COST_DUB_SEC", "300")),
    # per second of generated effect (estimate — ACE-Step not measurable)
    "sfx": float(_os.environ.get("PRAPTHI_COST_SFX_SEC", "200")),
    # per generated song (estimate — ACE-Step not measurable)
    "song": float(_os.environ.get("PRAPTHI_COST_SONG", "5000")),
}

OP_LABEL = {
    "stt": "transcription",
    "dub": "dubbing",
    "sfx": "sound effect",
    "song": "song",
}


def op_cost(op: str, seconds: float = 1.0) -> int:
    """Characters to charge for one use of `op`. Always at least 1."""
    rate = OP_COSTS[op]
    n = rate if op == "song" else rate * max(seconds, 0.0)
    return max(1, int(round(n)))


def too_expensive_message(op: str, need: int, left: int) -> str:
    what = OP_LABEL.get(op, op)
    return (f"This {what} needs {need:,} characters of your allowance and you "
            f"have {left:,} left. Shorten it, or upgrade your plan.")


# --- how much text each engine can actually render in time --------------- #
# Measured seconds per character on this CPU box, turned into a character cap
# that finishes inside ~600s (the proxy gives up at 900s).
# (seconds per character, seconds the engine's own client will wait). The
# caps come from the smaller of the two, with a 15% margin — a request that
# cannot finish before its client gives up must never be accepted.
_ENGINE_LIMITS = {
    "if5": (1.58, 300.0),          # IndicF5 HD — slowest by far
    "svara-": (0.26, 300.0),
    "chatterbox-": (0.165, 300.0),
    "parler-": (0.165, 300.0),
    "vagdhenu": (0.30, 600.0),
    "clone:": (0.165, 300.0),      # cloned voices render on Chatterbox
}


def max_chars_for(voice_id: str, default_cap: int) -> int:
    """Longest text this voice can render before its client times out."""
    vid = (voice_id or "").lower()
    for prefix, (rate, timeout) in _ENGINE_LIMITS.items():
        if vid.startswith(prefix):
            return max(120, min(default_cap, int(timeout * 0.85 / rate)))
    return default_cap



def too_long_message(voice_id: str, limit: int, given: int) -> str:
    return (f"This voice renders about {limit:,} characters at a time — you "
            f"sent {given:,}. Split the text, or pick one of the faster voices "
            f"for long passages.")
