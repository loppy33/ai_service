import asyncio
from html import escape
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.config import FROM_EMAIL
from app.core.deps import auth_dep, get_db
from app.core.mailer import mailer_configured, send_email
from app.models.lead import ContactRequest, Lead
from app.models.user import User

router = APIRouter(prefix="/leads", tags=["Leads"])


class ReportReq(BaseModel):
    email: EmailStr
    name: Optional[str] = Field(default=None, max_length=200)
    domain: Optional[str] = Field(default=None, max_length=300)
    geo: Optional[str] = Field(default=None, max_length=50)
    selected_queries: List[str] = Field(default_factory=list, max_length=50)


class ContactReq(BaseModel):
    email: EmailStr
    contact: Optional[str] = Field(default=None, max_length=200)
    name: Optional[str] = Field(default=None, max_length=200)


class OkResp(BaseModel):
    ok: bool


@router.post("/report-request", response_model=OkResp)
async def report_request(req: ReportReq, db: Session = Depends(get_db), _: User = Depends(auth_dep)):
    db.add(
        Lead(
            email=req.email,
            name=req.name,
            domain=req.domain,
            geo=req.geo,
            selected_queries=req.selected_queries,
        )
    )
    db.commit()

    if not mailer_configured():
        raise HTTPException(status_code=503, detail="Email delivery is not configured")

    queries_html = "".join(f"<li>{escape(q)}</li>" for q in req.selected_queries)
    greeting = f" {escape(req.name)}" if req.name else ""
    html = (
        f"<p>Hello{greeting}!</p>"
        f"<p>We received your request for {escape(req.domain or 'your site')} ({escape(req.geo or 'N/A')}).</p>"
        + (f"<p>Selected queries:</p><ul>{queries_html}</ul>" if queries_html else "")
        + "<p>We’ll prepare the report and follow up.</p>"
    )
    try:
        await asyncio.to_thread(send_email, req.email, "Your report and key visibility recommendations", html)
    except Exception as e:
        print(f"[Leads] email failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to send confirmation email")
    return OkResp(ok=True)


@router.post("/contact-request", response_model=OkResp)
async def contact_request(req: ContactReq, db: Session = Depends(get_db), _: User = Depends(auth_dep)):
    db.add(ContactRequest(email=req.email, contact=req.contact, name=req.name))
    db.commit()

    if mailer_configured():
        html = (
            "<p>New custom plan request</p>"
            f"<p>Email: {escape(req.email)}<br>Contact: {escape(req.contact or '-')}<br>Name: {escape(req.name or '-')}</p>"
        )
        try:
            await asyncio.to_thread(send_email, FROM_EMAIL, "Custom plan request", html)
        except Exception as e:
            print(f"[Leads] notify failed: {e}")
    return OkResp(ok=True)
