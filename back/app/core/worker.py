import asyncio
from datetime import datetime, timezone

import requests
from sqlalchemy import and_

from app.config.templates import TEMPLATES
from app.core.db import SessionLocal
from app.core.mailer import mailer_configured, send_email
from app.models.email_queue import EmailQueue
from app.models.user import User

POLL_INTERVAL_SEC = 60
MAX_ATTEMPTS = 5
PROVIDER_BLOCKING_STATUSES = (401, 403, 429)

_attempts: dict[int, int] = {}


def render_email(tpl: str, user: User, payload: dict):
    builder = TEMPLATES.get(tpl)
    if builder is None:
        raise ValueError(f"Unknown template: {tpl}")
    return builder(user.email, payload.get("project") or user.project_name)


def condition_ok(cond: str | None, user: User) -> bool:
    if not cond:
        return True
    if cond == "not_paid_but_logged_in":
        return user.last_seen_at is not None and user.paid_at is None
    return True


def _register_failure(session, job: EmailQueue, error: Exception) -> None:
    _attempts[job.id] = _attempts.get(job.id, 0) + 1
    print(f"[EmailQueue] send failed job={job.id} attempt={_attempts[job.id]}: {error}")
    if _attempts[job.id] >= MAX_ATTEMPTS:
        _attempts.pop(job.id, None)
        job.sent = True
        session.commit()


def _process_due_jobs() -> None:
    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        jobs = (
            session.query(EmailQueue)
            .filter(and_(EmailQueue.sent.is_(False), EmailQueue.send_at <= now))
            .order_by(EmailQueue.send_at.asc())
            .limit(50)
            .all()
        )
        for job in jobs:
            user = session.get(User, job.user_id)
            if not user or not condition_ok(job.condition, user):
                job.sent = True
                session.commit()
                continue
            try:
                subject, html = render_email(job.template, user, job.payload or {})
                send_email(user.email, subject, html)
            except ValueError as e:
                print(f"[EmailQueue] job={job.id} dropped: {e}")
                job.sent = True
                session.commit()
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status in PROVIDER_BLOCKING_STATUSES:
                    print(f"[EmailQueue] provider returned {status}, postponing the queue")
                    return
                _register_failure(session, job, e)
            except Exception as e:
                _register_failure(session, job, e)
            else:
                _attempts.pop(job.id, None)
                job.sent = True
                session.commit()
    finally:
        session.close()


async def worker_loop():
    if not mailer_configured():
        print("[Worker] SendPulse is not configured, email queue is idle")
    while True:
        if mailer_configured():
            try:
                await asyncio.to_thread(_process_due_jobs)
            except Exception as e:
                print(f"[Worker] loop error: {e}")
        await asyncio.sleep(POLL_INTERVAL_SEC)
