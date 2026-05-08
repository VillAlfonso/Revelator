"""Payment routes — Stripe (global) + PayMongo (Philippines).

Flow:
  1. Frontend calls POST /api/payments/create-checkout with {plan, payment_method}.
     Backend creates a checkout session and returns the redirect URL.
  2. User pays externally.
  3. Provider POSTs to our webhook with the result.
  4. We verify the signature and update the user's plan in Firestore.

Frontend reads the updated plan via the Firestore listener on `users/{uid}`
— no extra polling needed.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Optional

import requests
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import get_current_user
from ..config import (
    FRONTEND_URL,
    PAYMONGO_PUBLIC_KEY,
    PAYMONGO_SECRET_KEY,
    PAYMONGO_WEBHOOK_SECRET,
    PRO_PRICE_USD,
    PREMIUM_PRICE_USD,
    STRIPE_PRICE_ID_PREMIUM,
    STRIPE_PRICE_ID_PRO,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
)
from ..firebase_admin_init import db

router = APIRouter(prefix="/api/payments", tags=["payments"])

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def _now():
    return datetime.now(timezone.utc)


# ── Plans ──────────────────────────────────────────────────────────

@router.get("/plans")
def get_plans():
    return {
        "plans": [
            {
                "key": "free",
                "name": "Free",
                "price_usd": 0,
                "currency": "USD",
                "features": [
                    "10 scans / month",
                    "Analyst tier (Gemini Vision)",
                    "Document classification",
                ],
            },
            {
                "key": "pro",
                "name": "Pro",
                "price_usd": PRO_PRICE_USD,
                "currency": "USD",
                "features": [
                    "Unlimited scans",
                    "Detective tier (LLaVA + Gemini)",
                    "Priority processing",
                ],
            },
            {
                "key": "premium",
                "name": "Premium",
                "price_usd": PREMIUM_PRICE_USD,
                "currency": "USD",
                "features": [
                    "Unlimited scans",
                    "Sherlock tier (full LLaVA + document-aware)",
                    "AI-generated forensic explanation",
                    "Priority support",
                ],
            },
        ]
    }


@router.get("/paymongo-public-key")
def get_paymongo_public_key():
    return {"public_key": PAYMONGO_PUBLIC_KEY}


# ── Stripe checkout ────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str
    payment_method: str = "stripe"


@router.post("/create-checkout")
def create_checkout(body: CheckoutRequest, current_user: dict = Depends(get_current_user)):
    plan = body.plan.lower()
    if plan not in {"pro", "premium"}:
        raise HTTPException(400, "plan must be 'pro' or 'premium'")

    method = body.payment_method.lower()
    if method == "stripe":
        return _stripe_checkout(current_user, plan)
    if method == "paymongo":
        return _paymongo_checkout(current_user, plan)
    raise HTTPException(400, "payment_method must be 'stripe' or 'paymongo'")


def _stripe_checkout(user: dict, plan: str) -> dict:
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe is not configured")

    price_id = STRIPE_PRICE_ID_PRO if plan == "pro" else STRIPE_PRICE_ID_PREMIUM
    if not price_id:
        raise HTTPException(503, f"Stripe price ID for {plan} is not configured")

    customer_id = user.get("stripe_customer_id") or None
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.get("email") or None,
            name=user.get("full_name") or None,
            metadata={"firebase_uid": user["uid"]},
        )
        customer_id = customer.id
        db().collection("users").document(user["uid"]).update({
            "stripe_customer_id": customer_id, "updated_at": _now(),
        })

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{FRONTEND_URL}/account?payment=success",
        cancel_url=f"{FRONTEND_URL}/account?payment=cancelled",
        metadata={"firebase_uid": user["uid"], "plan": plan},
    )
    return {"checkout_url": session.url, "provider": "stripe"}


# ── PayMongo checkout ──────────────────────────────────────────────

def _paymongo_checkout(user: dict, plan: str) -> dict:
    if not PAYMONGO_SECRET_KEY:
        raise HTTPException(503, "PayMongo is not configured")

    # Convert USD price to PHP (rough: 1 USD ≈ 56 PHP). For production,
    # use the live FX rate or a fixed PHP price column on the plan.
    usd_price = PRO_PRICE_USD if plan == "pro" else PREMIUM_PRICE_USD
    php_centavos = int(round(usd_price * 56 * 100))

    auth = base64.b64encode(f"{PAYMONGO_SECRET_KEY}:".encode()).decode()
    payload = {
        "data": {
            "attributes": {
                "send_email_receipt": False,
                "show_description": True,
                "show_line_items": True,
                "line_items": [{
                    "currency": "PHP",
                    "amount": php_centavos,
                    "name": f"Revelator {plan.title()} (1 month)",
                    "quantity": 1,
                }],
                "payment_method_types": ["card", "gcash", "paymaya", "grab_pay"],
                "success_url": f"{FRONTEND_URL}/account?payment=success",
                "cancel_url": f"{FRONTEND_URL}/account?payment=cancelled",
                "metadata": {"firebase_uid": user["uid"], "plan": plan},
            }
        }
    }
    r = requests.post(
        "https://api.paymongo.com/v1/checkout_sessions",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json=payload, timeout=15,
    )
    if not r.ok:
        raise HTTPException(502, f"PayMongo error: {r.text[:200]}")
    data = r.json()["data"]
    return {
        "checkout_url": data["attributes"]["checkout_url"],
        "provider": "paymongo",
        "session_id": data["id"],
    }


# ── Webhooks ───────────────────────────────────────────────────────

@router.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Stripe webhook secret not configured")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(400, f"Webhook signature failed: {exc}")

    et = event["type"]
    obj = event["data"]["object"]

    if et == "checkout.session.completed":
        uid = (obj.get("metadata") or {}).get("firebase_uid")
        plan = (obj.get("metadata") or {}).get("plan")
        if uid and plan in {"pro", "premium"}:
            db().collection("users").document(uid).update({
                "plan": plan,
                "stripe_subscription_id": obj.get("subscription") or "",
                "scans_this_month": 0,
                "scan_reset_date": _now(),
                "updated_at": _now(),
            })
    elif et in ("customer.subscription.deleted", "customer.subscription.paused"):
        # Downgrade — find the user via stripe_customer_id
        cid = obj.get("customer")
        if cid:
            users = db().collection("users").where("stripe_customer_id", "==", cid).stream()
            for snap in users:
                snap.reference.update({"plan": "free", "updated_at": _now()})

    return {"received": True}


@router.post("/paymongo-webhook")
async def paymongo_webhook(request: Request):
    payload = await request.body()
    if PAYMONGO_WEBHOOK_SECRET:
        # PayMongo signs webhooks with HMAC-SHA256; verify in production.
        # The header is `Paymongo-Signature: t=…,te=…,li=…`.
        sig_header = request.headers.get("paymongo-signature", "")
        if not _paymongo_signature_valid(sig_header, payload, PAYMONGO_WEBHOOK_SECRET):
            raise HTTPException(400, "PayMongo webhook signature invalid")

    try:
        event = json.loads(payload.decode())
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    etype = (event.get("data") or {}).get("attributes", {}).get("type")
    data = (event.get("data") or {}).get("attributes", {}).get("data") or {}

    if etype == "checkout_session.payment.paid":
        meta = ((data.get("attributes") or {}).get("metadata") or {})
        uid = meta.get("firebase_uid")
        plan = meta.get("plan")
        if uid and plan in {"pro", "premium"}:
            db().collection("users").document(uid).update({
                "plan": plan,
                "scans_this_month": 0,
                "scan_reset_date": _now(),
                "updated_at": _now(),
            })

    return {"received": True}


def _paymongo_signature_valid(header: str, payload: bytes, secret: str) -> bool:
    import hashlib
    import hmac
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    timestamp = parts.get("t")
    signature = parts.get("li") or parts.get("te")
    if not timestamp or not signature:
        return False
    signed = f"{timestamp}.{payload.decode()}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
