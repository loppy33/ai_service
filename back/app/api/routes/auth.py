from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.deps import auth_dep, get_db
from app.core.security import create_access_token
from app.models.email_queue import EmailQueue
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])

MARKETING_SCHEDULE = (
    ("REMIND_2D", 2, "not_paid_but_logged_in"),
    ("CASES_5D", 5, None),
    ("BRIEF_9D", 9, None),
    ("REMIND_23D", 23, None),
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    projectName: str = Field(min_length=1, max_length=255)
    subscribe: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    token: str
    email: str
    projectName: str


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(token=create_access_token(user.id), email=user.email, projectName=user.project_name)


@router.post("/register", response_model=AuthResponse)
def register_user(req: RegisterRequest, db: Session = Depends(get_db)):
    email = req.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="User already exists")

    user = User(
        email=email,
        password=generate_password_hash(req.password),
        project_name=req.projectName.strip(),
        subscribe=req.subscribe,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="User already exists")

    now = datetime.now(timezone.utc)
    payload = {"project": user.project_name}
    jobs = [EmailQueue(user_id=user.id, send_at=now, template="REPORT", payload=payload)]
    if user.subscribe:
        jobs.extend(
            EmailQueue(
                user_id=user.id,
                send_at=now + timedelta(days=days),
                template=template,
                payload=payload,
                condition=condition,
            )
            for template, days, condition in MARKETING_SCHEDULE
        )
    db.add_all(jobs)
    db.commit()
    db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not check_password_hash(user.password, req.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_response(user)


@router.get("/me")
def get_me(current_user: User = Depends(auth_dep), db: Session = Depends(get_db)):
    current_user.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "email": current_user.email,
        "projectName": current_user.project_name,
        "paid": current_user.paid_at is not None,
    }
