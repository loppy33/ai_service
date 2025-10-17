from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import os, stripe

router = APIRouter(prefix="/billing", tags=["Billing"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")  # из кабинета Stripe
FRONT_RETURN_URL = os.getenv("FRONT_RETURN_URL", "http://localhost:5173/success")

class CheckoutReq(BaseModel):
    package_id: str   # "basic" | "pro"
    project_id: str

class CheckoutResp(BaseModel):
    url: str

@router.post("/create-checkout-session", response_model=CheckoutResp)
def create_checkout_session(req: CheckoutReq):
    prices = {
        "basic": os.getenv("STRIPE_PRICE_BASIC"),
        "pro": os.getenv("STRIPE_PRICE_PRO"),
    }
    price_id = prices.get(req.package_id)
    if not price_id:
        raise HTTPException(status_code=400, detail="Unknown package_id")

    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=f"{FRONT_RETURN_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{FRONT_RETURN_URL}?cancelled=1",
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={"project_id": req.project_id, "package_id": req.package_id}
    )
    return CheckoutResp(url=session.url)

@router.post("/webhook")
async def webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig, secret=endpoint_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # TODO: сохранить оплату в БД и триггернуть письмо/доступ в кабинет
        # session.get("metadata", {})
    return {"ok": True}
