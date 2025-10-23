from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.db import Base

class EmailQueue(Base):
    __tablename__ = "email_queue"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    send_at = Column(DateTime(timezone=True), nullable=False)
    template = Column(String(64), nullable=False)   # REPORT, REMIND_2D, CASES_5D, BRIEF_9D, REMIND_23D
    payload = Column(JSON, nullable=True)
    condition = Column(String(64), nullable=True)   # None | not_paid_but_logged_in
    sent = Column(Boolean, default=False, nullable=False)

    user = relationship("User")