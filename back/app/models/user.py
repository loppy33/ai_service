from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    project_name = Column(String(255), nullable=False)
    subscribe = Column(Boolean, default=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
