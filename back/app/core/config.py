import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[1]
load_dotenv(APP_DIR / ".env")

DATA_DIR = APP_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
TEMPLATES_PATH = APP_DIR / "config" / "mod_templates.yaml"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/aeo")

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "168"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_TIMEOUT_MS = int(os.getenv("OPENAI_TIMEOUT_MS", "45000"))

SENDPULSE_ID = os.getenv("SENDPULSE_ID", "")
SENDPULSE_SECRET = os.getenv("SENDPULSE_SECRET", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICES = {
    "basic": os.getenv("STRIPE_PRICE_BASIC", ""),
    "pro": os.getenv("STRIPE_PRICE_PRO", ""),
}
FRONT_RETURN_URL = os.getenv("FRONT_RETURN_URL", "http://localhost:5173/success")

CABINET_URL = os.getenv("CABINET_URL", "https://app.aeoagency.team/login")
TELEGRAM_URL = os.getenv("TELEGRAM_URL", "https://t.me/aeoagency_support")
PAY_URL = os.getenv("PAY_URL", "https://app.aeoagency.team/billing")
BRIEF_URL = os.getenv("BRIEF_URL", "https://app.aeoagency.team/brief-seo")

CHATGPT_HEADLESS = os.getenv("CHATGPT_HEADLESS", "0") == "1"
