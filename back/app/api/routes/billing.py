from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.core.config import FRONT_RETURN_URL, STRIPE_PRICES, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from app.core.db import SessionLocal
from app.core.deps import auth_dep
from app.models.user import User

router = APIRouter(prefix="/billing", tags=["Billing"])

stripe.api_key = STRIPE_SECRET_KEY


class CheckoutReq(BaseModel):
    package_id: str
    project_id: str = ""


class CheckoutResp(BaseModel):
    url: str


@router.post("/create-checkout-session", response_model=CheckoutResp)
def create_checkout_session(req: CheckoutReq, user: User = Depends(auth_dep)):
    price_id = STRIPE_PRICES.get(req.package_id)
    if not price_id:
        raise HTTPException(status_code=400, detail="Unknown package_id")
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payments are not configured")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=f"{FRONT_RETURN_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONT_RETURN_URL}?cancelled=1",
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=str(user.id),
            customer_email=user.email,
            metadata={"user_id": str(user.id), "project_id": req.project_id or user.project_name, "package_id": req.package_id},
        )
    except stripe.StripeError as e:
        print(f"[Stripe] checkout failed: {e}")
        raise HTTPException(status_code=502, detail="Payment provider error")
    if not session.url:
        raise HTTPException(status_code=502, detail="Payment provider returned no checkout URL")
    return CheckoutResp(url=session.url)


def _mark_paid(user_id: int) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user and user.paid_at is None:
            user.paid_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


@router.post("/webhook")
async def webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook is not configured")
    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig, secret=STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        ref = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
        if ref and str(ref).isdigit() and session.get("payment_status") == "paid":
            await run_in_threadpool(_mark_paid, int(ref))
    return {"ok": True}
