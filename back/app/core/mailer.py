# mailer.py
import os, requests
import re

SENDPULSE_ID = os.getenv("SENDPULSE_ID")
SENDPULSE_SECRET = os.getenv("SENDPULSE_SECRET")
FROM_EMAIL = os.getenv("FROM_EMAIL")  # подтверждённый в SMTP!

def _get_token() -> str:
    r = requests.post(
        "https://api.sendpulse.com/oauth/access_token",
        data={"grant_type":"client_credentials","client_id":SENDPULSE_ID,"client_secret":SENDPULSE_SECRET},
        timeout=10
    )
    r.raise_for_status()
    j = r.json()
    return j["access_token"]

def _html_to_text(s: str) -> str:
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p\s*>", "\n\n", s)
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()

def send_email(to_email: str, subject: str, html: str, text: str | None = None):
    if not html or not html.strip():
        raise ValueError("HTML body is empty")
    token = _get_token()
    text = text if (text and text.strip()) else _html_to_text(html)

    print(f"[Mailer] to={to_email} subj={subject!r} html_len={len(html)} text_len={len(text)}")

    payload = {
        "email": {
            "subject": subject,
            "html": html,
            "text": text,
            "from": {"name": "AEO Agency", "email": FROM_EMAIL},
            "to": [{"email": to_email}],
        }
    }

    r = requests.post(
        "https://api.sendpulse.com/smtp/emails",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        json=payload,
        timeout=15
    )
    if r.status_code == 422:
        raise RuntimeError(f"SendPulse 422: {r.text}")
    r.raise_for_status()
