"""Email delivery for Prapthi Ai.

Two modes (set VOXFORGE_EMAIL_MODE):
  * "console" (default) — prints the message to the server log. Lets the whole
    signup/verify/reset flow work end-to-end with no mail setup. Swap to SMTP
    later with zero code changes.
  * "smtp" — sends via your own/Gmail SMTP using stdlib smtplib (no third-party
    API). Configure VOXFORGE_SMTP_HOST/PORT/USER/PASSWORD/FROM.

All sends are best-effort and never raise into the request path.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

MODE = os.environ.get("VOXFORGE_EMAIL_MODE", "console").lower()
FROM = os.environ.get("VOXFORGE_SMTP_FROM", "Prapthi Ai <no-reply@ayaanvoice.local>")


def _send_smtp(to: str, subject: str, body: str) -> None:
    host = os.environ.get("VOXFORGE_SMTP_HOST", "")
    port = int(os.environ.get("VOXFORGE_SMTP_PORT", "587"))
    user = os.environ.get("VOXFORGE_SMTP_USER", "")
    password = os.environ.get("VOXFORGE_SMTP_PASSWORD", "")
    msg = EmailMessage()
    msg["From"] = FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=15) as s:
        s.starttls(context=ctx)
        if user:
            s.login(user, password)
        s.send_message(msg)


def send_email(to: str, subject: str, body: str) -> None:
    try:
        if MODE == "smtp":
            _send_smtp(to, subject, body)
        else:
            # Console/dev mode — visible in the server log.
            print(
                "\n===== [EMAIL] (console mode) =====\n"
                f"To: {to}\nSubject: {subject}\n\n{body}\n"
                "==================================\n"
            )
    except Exception as e:  # never break the request over email
        print(f"[voxforge][email] send failed to {to}: {e!r}")


# --- templates ------------------------------------------------------------- #
def send_verification(to: str, code: str) -> None:
    send_email(
        to,
        "Verify your Prapthi Ai account",
        f"Welcome to Prapthi Ai!\n\nYour verification code is: {code}\n\n"
        "Enter it on the verification screen to activate your account. "
        "It expires in 15 minutes.\n\nIf you didn't sign up, ignore this email.",
    )


def send_welcome(to: str) -> None:
    send_email(
        to,
        "Welcome to Prapthi Ai",
        "Your email is verified and your account is active. "
        "You can now sign in and start creating speech. Enjoy!",
    )


def send_login_alert(to: str) -> None:
    send_email(
        to,
        "New sign-in to Prapthi Ai",
        "Your Prapthi Ai account was just signed in to. "
        "If this was you, no action is needed. If not, reset your password "
        "immediately.",
    )


def send_reset(to: str, code: str) -> None:
    send_email(
        to,
        "Reset your Prapthi Ai password",
        f"Your password reset code is: {code}\n\n"
        "Enter it with your new password on the reset screen. "
        "It expires in 15 minutes.\n\nIf you didn't request this, ignore this email.",
    )
