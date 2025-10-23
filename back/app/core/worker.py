# worker.py
import asyncio
from datetime import datetime, timezone
from sqlalchemy import and_
from sqlalchemy.orm import Session
from app.core.db import SessionLocal
from app.core.mailer import send_email
from app.api.routes.auth import EmailQueue, User
from app.config.templates import (
    tpl_report, tpl_remind_2d, tpl_cases_5d, tpl_brief_9d, tpl_remind_23d
)

def render_email(tpl: str, user: User, payload: dict):
    if tpl == "REPORT":
        return tpl_report(user.email, payload["project"])
    if tpl == "REMIND_2D":
        return tpl_remind_2d(user.email, payload["project"])
    if tpl == "CASES_5D":
        return tpl_cases_5d(user.email, payload["project"])
    if tpl == "BRIEF_9D":
        return tpl_brief_9d(user.email, payload["project"])
    if tpl == "REMIND_23D":
        return tpl_remind_23d(user.email, payload["project"])
    raise ValueError(f"Unknown template: {tpl}")

def condition_ok(cond: str | None, user: User) -> bool:
    if not cond:
        return True
    if cond == "not_paid_but_logged_in":
        return (user.last_seen_at is not None) and (user.paid_at is None)
    return True

async def worker_loop():
    while True:
        try:
            s: Session = SessionLocal()
            now = datetime.now(timezone.utc)

            jobs = (
                s.query(EmailQueue)
                .filter(and_(EmailQueue.sent == False, EmailQueue.send_at <= now))
                .order_by(EmailQueue.send_at.asc())
                .limit(50)
                .all()
            )

            for job in jobs:
                user = s.query(User).get(job.user_id)
                if not user:
                    job.sent = True  # помечаем, чтобы не застрял
                    s.commit()
                    continue

                if not condition_ok(job.condition, user):
                    # Условие не выполнено — просто помечаем отправленным, чтобы не слал бесконечно
                    job.sent = True
                    s.commit()
                    continue

                subj, html = render_email(job.template, user, job.payload or {})
                try:
                    send_email(user.email, subj, html)
                    job.sent = True
                    s.commit()
                except Exception as e:
                    # логируй и оставь job неотправленным — попробуем в следующем цикле
                    print(f"[EmailQueue] send failed job={job.id}: {e}")

        except Exception as e:
            print(f"[Worker] loop error: {e}")
        finally:
            try:
                s.close()
            except:
                pass

        await asyncio.sleep(60)
