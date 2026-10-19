from sqlalchemy import JSON, Column, DateTime, Integer, String, func

from app.core.db import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    geo = Column(String, nullable=True)
    selected_queries = Column(JSON, nullable=True)


class ContactRequest(Base):
    __tablename__ = "contact_requests"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False)
    contact = Column(String, nullable=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
