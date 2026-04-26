"""
Stripe payment routes for subscription management.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..config import (
    STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_PREMIUM, FRONTEND_URL,
    PRO_PRICE_USD, PREMIUM_PRICE_USD,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])


def get_stripe():
    """Lazy import stripe so the app works even without the package."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured. Add STRIPE_SECRET_KEY to .env")
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        raise HTTPException(status_code=503, detail="stripe package not installed. Run: pip install stripe")


PLAN_PRICE_MAP = {
    "pro": STRIPE_PRICE_ID_PRO,
    "premium": STRIPE_PRICE_ID_PREMIUM,
}


class CheckoutRequest(BaseModel):
    plan: str  # "pro" or "premium"


@router.get("/plans")
def get_plans():
    return {
        "plans": [
            {
                "id": "free", "name": "Free", "price": 0,
                "scans_per_month": 10, "unlimited": False, "llm_included": False,
                "features": [
                    "10 scans / month",
                    "Verdict + bounding boxes",
                    "Scan history with images",
                    "Community support",
                ],
            },
            {
                "id": "pro", "name": "Pro", "price": PRO_PRICE_USD,
                "scans_per_month": -1, "unlimited": True, "llm_included": False,
                "features": [
                    "Unlimited scans",
                    "Verdict + bounding boxes",
                    "Scan history with images",
                    "Email support",
                ],
            },
            {
                "id": "premium", "name": "Premium", "price": PREMIUM_PRICE_USD,
                "scans_per_month": -1, "unlimited": True, "llm_included": True,
                "features": [
                    "Unlimited scans",
                    "AI forensic explanation on every scan",
                    "Priority processing",
                    "Priority support",
                ],
            },
        ]
    }


@router.post("/create-checkout")
def create_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stripe = get_stripe()

    price_id = PLAN_PRICE_MAP.get(body.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan. Choose 'pro' or 'premium'.")

    # Create or reuse Stripe customer
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            metadata={"user_id": current_user.id},
        )
        current_user.stripe_customer_id = customer.id
        db.commit()

    # Create checkout session
    session = stripe.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{FRONTEND_URL}/account?payment=success",
        cancel_url=f"{FRONTEND_URL}/account?payment=cancelled",
        metadata={"user_id": current_user.id, "plan": body.plan},
    )

    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    stripe = get_stripe()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        plan = session.get("metadata", {}).get("plan", "basic")
        subscription_id = session.get("subscription")

        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.plan = plan
                user.stripe_subscription_id = subscription_id
                db.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        subscription_id = sub.get("id")
        user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
        if user:
            user.plan = "free"
            user.stripe_subscription_id = None
            db.commit()

    return {"status": "ok"}


@router.post("/cancel")
def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription")

    stripe = get_stripe()
    stripe.Subscription.modify(current_user.stripe_subscription_id, cancel_at_period_end=True)
    return {"message": "Subscription will cancel at end of billing period"}
