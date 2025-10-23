# routers/auth.py
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta, timezone

from app.core.deps import auth_dep, get_db
from app.models.user import User
from app.models.email_queue import EmailQueue
from app.config.templates import (
    tpl_report, tpl_remind_2d, tpl_cases_5d, tpl_brief_9d, tpl_remind_23d
)

router = APIRouter(prefix="/auth", tags=["Auth"])

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    projectName: str
    subscribe: bool = False

class RegisterResponse(BaseModel):
    message: str

@router.post("/register", response_model=RegisterResponse)
def register_user(req: RegisterRequest, db: Session = Depends(get_db)):
    try:
        if db.query(User).filter_by(email=req.email).first():
            raise HTTPException(status_code=400, detail="User already exists")

        hashed_password = generate_password_hash(req.password)

        user = User(
            email=req.email,
            password=hashed_password,
            project_name=req.projectName,
            subscribe=req.subscribe
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # План писем
        now = datetime.now(timezone.utc)
        jobs = [
            EmailQueue(user_id=user.id, send_at=now,                   template="REPORT",    payload={"project": user.project_name}),
            EmailQueue(user_id=user.id, send_at=now + timedelta(days=2),  template="REMIND_2D", payload={"project": user.project_name}, condition="not_paid_but_logged_in"),
            EmailQueue(user_id=user.id, send_at=now + timedelta(days=5),  template="CASES_5D",  payload={"project": user.project_name}),
            EmailQueue(user_id=user.id, send_at=now + timedelta(days=9),  template="BRIEF_9D",  payload={"project": user.project_name}),
            EmailQueue(user_id=user.id, send_at=now + timedelta(days=23), template="REMIND_23D",payload={"project": user.project_name}),
        ]
        db.add_all(jobs)
        db.commit()

        return {"message": "User registered successfully"}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="User already exists")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

@router.get("/me")
def get_me(current_user: User = Depends(auth_dep), db: Session = Depends(get_db)):
    u = db.get(User, current_user.id)  # SQLAlchemy 2.x способ
    if u:
        u.last_seen_at = datetime.now(timezone.utc)
        db.commit()
    return {"email": current_user.email}
