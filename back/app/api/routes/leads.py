from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import os, time, requests

from sqlalchemy import create_engine, Column, Integer, String, Boolean, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
load_dotenv()
# 🔹 подключение к PostgreSQL
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
    # save lead
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

    sp_id = os.getenv("SENDPULSE_ID")
    sp_secret = os.getenv("SENDPULSE_SECRET")
    from_email = os.getenv("FROM_EMAIL", "noreply@yourdomain.com")

    # отправка письма — c диагностикой
    if not (sp_id and sp_secret):
        # Нет ключей — сообщаем явно (или логируем и продолжаем)
        raise HTTPException(status_code=500, detail="SendPulse API keys are not configured")

    try:
        # 1) OAuth
        token_resp = requests.post(
            "https://api.sendpulse.com/oauth/access_token",
            data={
                "grant_type": "client_credentials",
                "client_id": sp_id,
                "client_secret": sp_secret
            },
            timeout=10
        )
        if token_resp.status_code != 200:
            raise RuntimeError(f"OAuth failed: {token_resp.status_code} {token_resp.text}")

        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise RuntimeError(f"No access_token in response: {token_resp.text}")

        # 2) Письмо
        subject = "Your report and key visibility recommendations"
        selected = "\n- " + "\n- ".join(req.selected_queries or []) if (req.selected_queries) else ""
        text = (
            f"Hello{(' ' + req.name) if req.name else ''}!\n\n"
            f"We received your request for {req.domain or 'your site'} ({req.geo or 'N/A'}).\n"
            f"Selected queries:{selected}\n\n"
            "We’ll prepare the report and follow up.\n"
        )

        email_resp = requests.post(
            "https://api.sendpulse.com/smtp/emails",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            json={
                "email": {
                    "subject": subject,
                    "text": text,
                    # можно добавить "html" для лучшей доставки
                    "from": {"name": "AEO Agency", "email": from_email},
                    "to": [{"email": req.email}]
                }
            },
            timeout=15
        )
        print(from_email)

        if email_resp.status_code not in (200, 201, 202):
            # вернём подробности — это поможет понять, что именно не понравилось API
            raise RuntimeError(f"Send email failed: {email_resp.status_code} {email_resp.text}")

    except Exception as e:
        # логируй в Sentry/лог файлы
        print(f"[SendPulse] error: {e}")
        # можно вернуть ok=False, чтобы фронт показал предупреждение
        raise HTTPException(status_code=502, detail="Failed to send confirmation email")

    return ReportResp(ok=True)
