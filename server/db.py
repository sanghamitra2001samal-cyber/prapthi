"""PostgreSQL data layer for Prapthi Ai accounts.

Async connection pool (psycopg 3) + schema bootstrap + user/code repositories.
Stores users, email verification codes, and password-reset codes. No plaintext
secrets: password hashes are scrypt records (JSON), codes are stored as SHA-256.

Connection string via VOXFORGE_DATABASE_URL (default: local socket, db
``ayaanvoice``). The pool is opened/closed by the app lifespan.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

DSN = os.environ.get("VOXFORGE_DATABASE_URL", "postgresql:///ayaanvoice")

# Pool is created here but opened in the app lifespan (open=False avoids a
# deprecation warning about opening in the constructor).
pool = AsyncConnectionPool(
    DSN, open=False, min_size=1, max_size=10, kwargs={"row_factory": dict_row}
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,                 -- JSON scrypt record
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    session_version INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS email_codes (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT NOT NULL,
    purpose     TEXT NOT NULL,                     -- 'verify' | 'reset'
    code_hash   TEXT NOT NULL,                     -- sha256(code)
    expires_at  TIMESTAMPTZ NOT NULL,
    used        BOOLEAN NOT NULL DEFAULT FALSE,
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_codes ON email_codes (email, purpose);

CREATE TABLE IF NOT EXISTS cloned_voices (
    id          TEXT PRIMARY KEY,                  -- uuid (also the file stem)
    owner       TEXT NOT NULL,                     -- user email
    name        TEXT NOT NULL,
    lang        TEXT NOT NULL DEFAULT 'en',        -- Chatterbox language_id
    path        TEXT NOT NULL,                     -- absolute wav path on disk
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cloned_owner ON cloned_voices (owner);

CREATE TABLE IF NOT EXISTS payments (
    payment_id   TEXT PRIMARY KEY,            -- Razorpay's id: credit once, ever
    order_id     TEXT NOT NULL,
    email        TEXT NOT NULL,
    plan         TEXT NOT NULL,
    amount_paise BIGINT NOT NULL,
    source       TEXT NOT NULL,               -- 'callback' or 'webhook'
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS payments_email_idx ON payments (email);

ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS chars_allowance BIGINT NOT NULL DEFAULT 12000;
ALTER TABLE users ADD COLUMN IF NOT EXISTS chars_used BIGINT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS period_start TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS songs (
    id               TEXT PRIMARY KEY,             -- uuid (also the job id)
    owner            TEXT NOT NULL,
    title            TEXT NOT NULL DEFAULT 'Untitled',
    script           TEXT NOT NULL DEFAULT '',
    lyrics           TEXT NOT NULL DEFAULT '',
    genre            TEXT NOT NULL DEFAULT 'pop',
    language         TEXT NOT NULL DEFAULT 'en',
    voice_id         TEXT NOT NULL DEFAULT '',
    emotion          TEXT NOT NULL DEFAULT 'neutral',
    emotion_json     TEXT NOT NULL DEFAULT '{}',
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'queued', -- queued|processing|done|failed
    progress         INTEGER NOT NULL DEFAULT 0,
    current_step     TEXT NOT NULL DEFAULT 'Queued',
    error            TEXT,
    audio_path       TEXT,
    parent_id        TEXT,
    stems_status     TEXT NOT NULL DEFAULT 'none',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_songs_owner ON songs (owner, created_at);
"""

# Idempotent column adds for existing deployments.
_MIGRATIONS = [
    "ALTER TABLE songs ADD COLUMN IF NOT EXISTS parent_id TEXT",
    "ALTER TABLE songs ADD COLUMN IF NOT EXISTS stems_status TEXT NOT NULL DEFAULT 'none'",
]


async def init_db() -> None:
    await pool.open()
    async with pool.connection() as conn:
        await conn.execute(_SCHEMA)
        for m in _MIGRATIONS:
            try:
                await conn.execute(m)
            except Exception as e:  # pragma: no cover
                print(f"[db] migration skipped: {e!r}")


async def close_db() -> None:
    await pool.close()


# --- users ----------------------------------------------------------------- #
async def get_user(email: str) -> Optional[dict[str, Any]]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM users WHERE email = %s", (email.lower(),)
        )
        return await cur.fetchone()


async def create_user(email: str, password_hash: dict, is_admin: bool = False) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO users (email, password_hash, is_admin) VALUES (%s, %s, %s)",
            (email.lower(), json.dumps(password_hash), is_admin),
        )


async def set_password(email: str, password_hash: dict) -> None:
    async with pool.connection() as conn:
        # Changing the password also revokes all existing sessions.
        await conn.execute(
            "UPDATE users SET password_hash = %s, "
            "session_version = session_version + 1 WHERE email = %s",
            (json.dumps(password_hash), email.lower()),
        )


async def mark_verified(email: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE users SET is_verified = TRUE WHERE email = %s", (email.lower(),)
        )


async def bump_session_version(email: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE users SET session_version = session_version + 1 WHERE email = %s",
            (email.lower(),),
        )


async def touch_login(email: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE users SET last_login_at = now() WHERE email = %s", (email.lower(),)
        )


def password_record(user: dict) -> dict:
    """Decode the stored scrypt JSON record."""
    raw = user["password_hash"]
    return raw if isinstance(raw, dict) else json.loads(raw)


# --- email codes ----------------------------------------------------------- #
async def store_code(email: str, purpose: str, code_hash: str, ttl_seconds: int) -> None:
    async with pool.connection() as conn:
        # Invalidate any previous unused codes for this email+purpose first.
        await conn.execute(
            "UPDATE email_codes SET used = TRUE WHERE email = %s AND purpose = %s "
            "AND used = FALSE",
            (email.lower(), purpose),
        )
        await conn.execute(
            "INSERT INTO email_codes (email, purpose, code_hash, expires_at) "
            "VALUES (%s, %s, %s, now() + (%s || ' seconds')::interval)",
            (email.lower(), purpose, code_hash, ttl_seconds),
        )


async def consume_code(email: str, purpose: str, code_hash: str) -> bool:
    """Return True if a valid, unexpired, unused code matches; marks it used.
    Counts attempts and rejects after too many to thwart brute force."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, code_hash, attempts FROM email_codes "
            "WHERE email = %s AND purpose = %s AND used = FALSE "
            "AND expires_at > now() ORDER BY created_at DESC LIMIT 1",
            (email.lower(), purpose),
        )
        row = await cur.fetchone()
        if not row:
            return False
        if row["attempts"] >= 5:
            await conn.execute(
                "UPDATE email_codes SET used = TRUE WHERE id = %s", (row["id"],)
            )
            return False
        if row["code_hash"] != code_hash:
            await conn.execute(
                "UPDATE email_codes SET attempts = attempts + 1 WHERE id = %s",
                (row["id"],),
            )
            return False
        await conn.execute(
            "UPDATE email_codes SET used = TRUE WHERE id = %s", (row["id"],)
        )
        return True


# --- cloned voices --------------------------------------------------------- #
async def add_clone(vid: str, owner: str, name: str, lang: str, path: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO cloned_voices (id, owner, name, lang, path) "
            "VALUES (%s, %s, %s, %s, %s)",
            (vid, owner.lower(), name, lang, path),
        )


async def list_clones(owner: str) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, name, lang, path FROM cloned_voices "
            "WHERE owner = %s ORDER BY created_at DESC",
            (owner.lower(),),
        )
        return await cur.fetchall()


async def get_clone(vid: str, owner: str) -> Optional[dict[str, Any]]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, name, lang, path FROM cloned_voices "
            "WHERE id = %s AND owner = %s",
            (vid, owner.lower()),
        )
        return await cur.fetchone()


async def count_clones(owner: str) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) AS n FROM cloned_voices WHERE owner = %s",
            (owner.lower(),),
        )
        row = await cur.fetchone()
        return int(row["n"]) if row else 0


async def delete_clone(vid: str, owner: str) -> Optional[str]:
    """Delete a clone row; returns its file path so the caller can unlink it."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM cloned_voices WHERE id = %s AND owner = %s RETURNING path",
            (vid, owner.lower()),
        )
        row = await cur.fetchone()
        return row["path"] if row else None


# --- songs (EmotionSong) --------------------------------------------------- #
async def create_song(
    sid: str, owner: str, title: str, script: str, lyrics: str, genre: str,
    language: str, voice_id: str, emotion: str, emotion_json: str,
    parent_id: str | None = None,
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO songs (id, owner, title, script, lyrics, genre, language, "
            "voice_id, emotion, emotion_json, parent_id, status, progress, current_step) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',0,'Queued')",
            (sid, owner.lower(), title, script, lyrics, genre, language,
             voice_id, emotion, emotion_json, parent_id),
        )


async def update_song(sid: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = %s" for k in fields)
    async with pool.connection() as conn:
        await conn.execute(
            f"UPDATE songs SET {cols} WHERE id = %s",
            (*fields.values(), sid),
        )


async def get_song(sid: str, owner: str) -> Optional[dict[str, Any]]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM songs WHERE id = %s AND owner = %s AND deleted_at IS NULL",
            (sid, owner.lower()),
        )
        return await cur.fetchone()


async def list_songs(owner: str) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, title, genre, language, voice_id, emotion, status, progress, "
            "current_step, duration_seconds, created_at FROM songs "
            "WHERE owner = %s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100",
            (owner.lower(),),
        )
        return await cur.fetchall()


async def delete_song(sid: str, owner: str) -> Optional[str]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE songs SET deleted_at = now() WHERE id = %s AND owner = %s "
            "AND deleted_at IS NULL RETURNING audio_path",
            (sid, owner.lower()),
        )
        row = await cur.fetchone()
        return row["audio_path"] if row else None


# --- account deletion ------------------------------------------------------ #
async def delete_account(email: str) -> dict[str, Any]:
    """Erase an account and everything it owns, in one transaction.

    Payment records are kept on purpose: Indian tax and accounting law require
    a business to keep its sales records, so the ledger outlives the account.
    Returns the deleted clones and songs so the caller can remove their files
    (files are not transactional, so they go only after the rows are gone).
    """
    email = email.lower()
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "DELETE FROM cloned_voices WHERE owner = %s RETURNING id, path", (email,)
            )
            clones = await cur.fetchall()
            cur = await conn.execute(
                "DELETE FROM songs WHERE owner = %s RETURNING id, audio_path", (email,)
            )
            songs = await cur.fetchall()
            await conn.execute("DELETE FROM email_codes WHERE email = %s", (email,))
            cur = await conn.execute(
                "DELETE FROM users WHERE email = %s RETURNING id", (email,)
            )
            gone = await cur.fetchone()
    return {"deleted": gone is not None, "clones": clones, "songs": songs}


# --- billing ---------------------------------------------------------- #
async def mark_paid(payment_id: str, order_id: str, email: str, plan: str,
                    amount_paise: int, source: str, allowance: int,
                    days: int) -> bool:
    """Record a payment and grant the plan. Returns True only the FIRST time a
    given payment id is seen, so a webhook arriving after the browser callback
    (or vice versa) cannot grant twice."""
    async with pool.connection() as conn:
        row = await (await conn.execute(
            """INSERT INTO payments (payment_id, order_id, email, plan,
                                     amount_paise, source)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (payment_id) DO NOTHING
               RETURNING payment_id""",
            (payment_id, order_id, email, plan, amount_paise, source),
        )).fetchone()
        if row is None:
            return False          # already credited
        await conn.execute(
            """UPDATE users
                  SET plan = %s,
                      chars_allowance = %s,
                      chars_used = 0,
                      period_start = now(),
                      plan_expires_at = now() + (%s || ' days')::interval
                WHERE email = %s""",
            (plan, allowance, days, email),
        )
        return True


async def get_account(email: str) -> Optional[dict[str, Any]]:
    """Plan + allowance for the billing screen. Expired paid plans read as free
    so the UI never shows an entitlement the server would not honour."""
    async with pool.connection() as conn:
        row = await (await conn.execute(
            """SELECT plan, chars_allowance, chars_used, period_start,
                      plan_expires_at, is_admin,
                      (plan_expires_at IS NOT NULL AND plan_expires_at < now())
                        AS expired
                 FROM users WHERE email = %s""",
            (email,),
        )).fetchone()
    return dict(row) if row else None


async def consume_chars(email: str, n: int) -> tuple[bool, int]:
    """Charge `n` characters against the monthly allowance.

    Returns (allowed, remaining). The check and the deduction happen in ONE
    statement so two concurrent requests cannot both spend the last of it.
    An expired paid plan falls back to the free allowance."""
    async with pool.connection() as conn:
        row = await (await conn.execute(
            """UPDATE users
                  SET chars_used = chars_used + %s
                WHERE email = %s
                  AND chars_used + %s <= (
                        CASE WHEN plan_expires_at IS NOT NULL
                              AND plan_expires_at < now()
                             THEN 12000 ELSE chars_allowance END)
            RETURNING chars_used,
                      CASE WHEN plan_expires_at IS NOT NULL
                            AND plan_expires_at < now()
                           THEN 12000 ELSE chars_allowance END AS allowance""",
            (n, email, n),
        )).fetchone()
    if row is None:
        return False, 0
    return True, int(row["allowance"]) - int(row["chars_used"])


async def reset_period_if_due(email: str) -> None:
    """Allowances are monthly: roll the counter once 30 days have passed."""
    async with pool.connection() as conn:
        await conn.execute(
            """UPDATE users SET chars_used = 0, period_start = now()
                WHERE email = %s AND period_start < now() - interval '30 days'""",
            (email,),
        )


async def refund_chars(email: str, n: int) -> None:
    """Return characters to an allowance after a job failed. Never goes below
    zero, so a double refund cannot manufacture allowance."""
    if n <= 0:
        return
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE users SET chars_used = GREATEST(0, chars_used - %s) "
            "WHERE email = %s",
            (n, email),
        )


# --- admin reporting ---------------------------------------------------- #
async def admin_stats() -> dict[str, Any]:
    """Counts an owner actually wants: signups, real logins, usage, revenue.

    One round trip per block rather than one giant query, because the blocks
    are independent and this stays readable as it grows."""
    async with pool.connection() as conn:
        async def one(sql, args=()):
            return await (await conn.execute(sql, args)).fetchone()

        async def many(sql, args=()):
            return [dict(r) for r in await (await conn.execute(sql, args)).fetchall()]

        totals = await one("""
            SELECT count(*)                                              AS users,
                   count(*) FILTER (WHERE is_verified)                   AS verified,
                   count(*) FILTER (WHERE is_admin)                      AS admins,
                   count(*) FILTER (WHERE last_login_at IS NOT NULL)     AS ever_logged_in,
                   count(*) FILTER (WHERE created_at > now() - interval '24 hours') AS new_today,
                   count(*) FILTER (WHERE created_at > now() - interval '7 days')   AS new_week,
                   count(*) FILTER (WHERE created_at > now() - interval '30 days')  AS new_month,
                   count(*) FILTER (WHERE last_login_at > now() - interval '24 hours') AS active_today,
                   count(*) FILTER (WHERE last_login_at > now() - interval '7 days')   AS active_week,
                   count(*) FILTER (WHERE last_login_at > now() - interval '30 days')  AS active_month
              FROM users""")

        usage = await one("""
            SELECT coalesce(sum(chars_used), 0)::bigint   AS chars_used,
                   coalesce(sum(chars_allowance), 0)::bigint AS chars_allowance,
                   count(*) FILTER (WHERE chars_used > 0) AS users_who_generated
              FROM users""")

        plans = await many("""
            SELECT plan,
                   count(*) AS users,
                   coalesce(sum(chars_used), 0)::bigint AS chars_used
              FROM users GROUP BY plan ORDER BY count(*) DESC""")

        # a daily series for the last 30 days, with empty days filled in
        signups = await many("""
            SELECT to_char(d.day, 'YYYY-MM-DD') AS day,
                   count(u.email)               AS signups
              FROM generate_series(
                     (now() - interval '29 days')::date, now()::date, interval '1 day') AS d(day)
              LEFT JOIN users u ON u.created_at::date = d.day
             GROUP BY d.day ORDER BY d.day""")

        logins = await many("""
            SELECT to_char(d.day, 'YYYY-MM-DD') AS day,
                   count(u.email)               AS logins
              FROM generate_series(
                     (now() - interval '29 days')::date, now()::date, interval '1 day') AS d(day)
              LEFT JOIN users u ON u.last_login_at::date = d.day
             GROUP BY d.day ORDER BY d.day""")

        top = await many("""
            SELECT email, plan, chars_used, chars_allowance,
                   to_char(created_at,  'YYYY-MM-DD HH24:MI') AS created_at,
                   to_char(last_login_at,'YYYY-MM-DD HH24:MI') AS last_login_at,
                   is_verified
              FROM users
             ORDER BY chars_used DESC, created_at DESC
             LIMIT 25""")

        recent = await many("""
            SELECT email, plan, is_verified,
                   to_char(created_at,  'YYYY-MM-DD HH24:MI') AS created_at,
                   to_char(last_login_at,'YYYY-MM-DD HH24:MI') AS last_login_at
              FROM users ORDER BY created_at DESC LIMIT 15""")

        revenue = await one("""
            SELECT count(*) AS payments,
                   coalesce(sum(amount_paise), 0)::bigint AS paise,
                   count(*) FILTER (WHERE created_at > now() - interval '30 days') AS payments_month,
                   coalesce(sum(amount_paise) FILTER (
                       WHERE created_at > now() - interval '30 days'), 0)::bigint AS paise_month
              FROM payments""")

        payments = await many("""
            SELECT email, plan, amount_paise, source,
                   to_char(created_at, 'YYYY-MM-DD HH24:MI') AS created_at
              FROM payments ORDER BY created_at DESC LIMIT 15""")

        clones = await one("SELECT count(*) AS n FROM cloned_voices")
        songs = await one("SELECT count(*) AS n FROM songs")

    return {
        "totals": dict(totals), "usage": dict(usage), "plans": plans,
        "signups_daily": signups, "logins_daily": logins,
        "top_users": top, "recent_users": recent,
        "revenue": dict(revenue), "recent_payments": payments,
        "clones": clones["n"], "songs": songs["n"],
    }
