from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import os, time, requests

from sqlalchemy import create_engine, Column, Integer, String, Boolean, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/aeo")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

router = APIRouter(prefix="/leads", tags=["Leads"])

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    geo = Column(String, nullable=True)
    selected_queries = Column(JSON, nullable=True)

Base.metadata.create_all(bind=engine)

class ReportReq(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    domain: Optional[str] = None
    geo: Optional[str] = None
    selected_queries: Optional[List[str]] = []

class ReportResp(BaseModel):
    ok: bool

@router.post("/report-request", response_model=ReportResp)
def report_request(req: ReportReq):
    # save
    s = SessionLocal()
    try:
        lead = Lead(
            email=req.email,
            name=req.name,
            domain=req.domain,
            geo=req.geo,
            selected_queries=req.selected_queries or []
        )
        s.add(lead)
        s.commit()
    finally:
        s.close()

    # send email via SendPulse (client_credentials)
    try:
        sp_id = os.getenv("SENDPULSE_ID")
        sp_secret = os.getenv("SENDPULSE_SECRET")
        if sp_id and sp_secret:
            token_resp = requests.post(
                "https://api.sendpulse.com/oauth/access_token",
                data={"grant_type":"client_credentials","client_id":sp_id,"client_secret":sp_secret},
                timeout=10
            ).json()
            access_token = token_resp.get("access_token")
            if access_token:
                # простой transactional email через SMTP-сендпульс API v1/email
                subject = "Your report and key visibility recommendations"
                text = (
                    f"Hello{(' ' + req.name) if req.name else ''}!\n\n"
                    f"We received your request for {req.domain or 'your site'} ({req.geo}).\n"
                    f"Selected queries:\n- " + "\n- ".join(req.selected_queries or []) + "\n\n"
                    "We’ll prepare the report and follow up.\n"
                )
                requests.post(
                    "https://api.sendpulse.com/smtp/emails",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={
                        "email": {
                            "subject": subject,
                            "text": text,
                            "to": [{"email": req.email}],
                            "from": {"name": "AEO Agency", "email": os.getenv("FROM_EMAIL", "noreply@yourdomain.com")}
                        }
                    },
                    timeout=10
                )
    except Exception:
        # не падаем, письмо – best-effort
        pass

    return ReportResp(ok=True)
