# mailer.py
import os, requests

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

def send_email(to_email: str, subject: str, html: str, text: str = None):
    token = _get_token()
    payload = {
        "email": {
            "subject": subject,
            "html": html,
            "text": text or "",
            "from": {"name": "AEO Agency", "email": FROM_EMAIL},
            "to": [{"email": to_email}],
        }
    }
    r = requests.post(
        "https://api.sendpulse.com/smtp/emails",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=15
    )
    if r.status_code == 422:
        raise RuntimeError(f"SendPulse 422: {r.text}")
    r.raise_for_status()
