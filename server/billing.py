"""Razorpay payments and the character allowance behind them.

Plans mirror the public pricing page exactly, so a customer is charged what the
site promises. Money rules that matter:

  * The amount ALWAYS comes from PLANS here, never from the browser — a request
    can ask for a plan, never for a price.
  * A plan is granted only after the server recomputes
    HMAC_SHA256(order_id|payment_id, key_secret) and it matches Razorpay's
    signature. The browser's word is never enough.
  * The webhook (HMAC over the raw body) is authoritative, because the browser
    callback can be lost — a customer who pays and closes the tab still gets
    credited.
  * Both paths funnel into db.mark_paid(), whose conditional UPDATE returns True
    only once per payment id, so a double confirmation credits exactly once.

No Razorpay SDK: plain REST over urllib and stdlib hmac, matching how the rest
of this server talks to services.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
API = "https://api.razorpay.com/v1"

# id -> what the pricing page advertises. `chars` is the monthly allowance.
PLANS: dict[str, dict] = {
    "free":  {"name": "No Cap", "price": 0,    "chars": 12_000,
              "blurb": "For trying things out and small personal projects."},
    "mid":   {"name": "Mid",    "price": 599,  "chars": 35_000,
              "blurb": "For creators, freelancers and growing channels."},
    "elite": {"name": "Elite",  "price": 1799, "chars": 300_000,
              "blurb": "For studios and teams publishing at serious scale."},
}
PLAN_DAYS = 30


def enabled() -> bool:
    """Payments only work once real keys are present in the environment."""
    return bool(KEY_ID and KEY_SECRET)


def public_plans() -> list[dict]:
    """Plans a customer may be shown. Hidden plans exist for internal testing
    and must never reach the pricing page."""
    return [{"id": pid, "name": p["name"], "price": p["price"],
             "chars": p["chars"], "blurb": p["blurb"]}
            for pid, p in PLANS.items() if not p.get("hidden")]


def _auth_header() -> str:
    raw = f"{KEY_ID}:{KEY_SECRET}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def create_order(plan_id: str, email: str) -> dict:
    """Ask Razorpay for an order. Amount comes from PLANS, never the caller."""
    plan = PLANS.get(plan_id)
    if not plan:
        raise ValueError("unknown plan")
    if plan["price"] <= 0:
        raise ValueError("that plan is free — nothing to pay")
    if not enabled():
        raise RuntimeError("payments are not switched on")

    body = json.dumps({
        "amount": plan["price"] * 100,          # paise
        "currency": "INR",
        "receipt": f"{plan_id}:{email}"[:40],
        "notes": {"plan": plan_id, "email": email},
    }).encode()
    req = urllib.request.Request(
        f"{API}/orders", data=body,
        headers={"Content-Type": "application/json", "Authorization": _auth_header()},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            order = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode("utf-8", "ignore")
        raise RuntimeError(f"Razorpay rejected the order: {detail}") from e
    return {
        "order_id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "key_id": KEY_ID,
        "plan": plan_id,
        "name": plan["name"],
    }


def verify_payment(order_id: str, payment_id: str, signature: str) -> bool:
    """Razorpay signs `order_id|payment_id` with the key secret."""
    if not (order_id and payment_id and signature and KEY_SECRET):
        return False
    expected = hmac.new(KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook(raw_body: bytes, signature: str) -> bool:
    """Webhooks are signed over the exact bytes received."""
    if not (signature and WEBHOOK_SECRET):
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def fetch_order(order_id: str) -> dict | None:
    """Read an order back from Razorpay — used to learn its plan and payer."""
    if not enabled():
        return None
    req = urllib.request.Request(f"{API}/orders/{order_id}",
                                 headers={"Authorization": _auth_header()})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception:
        return None
