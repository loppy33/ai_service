from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base


class EmailQueue(Base):
    __tablename__ = "email_queue"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    send_at = Column(DateTime(timezone=True), nullable=False)
    template = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=True)
    condition = Column(String(64), nullable=True)
    sent = Column(Boolean, default=False, nullable=False)

    user = relationship("User")
