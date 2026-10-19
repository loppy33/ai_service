import re

import requests

from app.core.config import FROM_EMAIL, SENDPULSE_ID, SENDPULSE_SECRET

OAUTH_URL = "https://api.sendpulse.com/oauth/access_token"
SEND_URL = "https://api.sendpulse.com/smtp/emails"


def mailer_configured() -> bool:
    return bool(SENDPULSE_ID and SENDPULSE_SECRET and FROM_EMAIL)


def _get_token() -> str:
    r = requests.post(
        OAUTH_URL,
        data={"grant_type": "client_credentials", "client_id": SENDPULSE_ID, "client_secret": SENDPULSE_SECRET},
        timeout=10,
    )
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError("SendPulse returned no access_token")
    return token


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p\s*>", "\n\n", s)
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def send_email(to_email: str, subject: str, html: str, text: str | None = None) -> None:
    if not mailer_configured():
        raise RuntimeError("SendPulse is not configured")
    if not html or not html.strip():
        raise ValueError("HTML body is empty")

    token = _get_token()
    payload = {
        "email": {
            "subject": subject,
            "html": html,
            "text": text if (text and text.strip()) else _html_to_text(html),
            "from": {"name": "AEO Agency", "email": FROM_EMAIL},
            "to": [{"email": to_email}],
        }
    }
    r = requests.post(
        SEND_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        json=payload,
        timeout=15,
    )
    if r.status_code == 422:
        raise ValueError(f"SendPulse rejected the email: {r.text}")
    r.raise_for_status()
