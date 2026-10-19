from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.security import decode_access_token
from app.models.user import User


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def auth_dep(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No token provided")
    user_id = decode_access_token(authorization[len("Bearer "):].strip())
    user = db.get(User, user_id) if user_id is not None else None
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user
