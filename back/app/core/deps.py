# deps.py
from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from app.core.db import SessionLocal
from app.models.user import User

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def auth_dep(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    """
    Упрощённо: "Bearer <email>".
    Заменишь на JWT при интеграции реальной авторизации.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No token provided")
    token = authorization.split("Bearer ")[1]
    user = db.query(User).filter_by(email=token).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user
