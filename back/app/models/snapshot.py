from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, UniqueConstraint

from app.core.db import Base


class VisibilitySnapshot(Base):
    __tablename__ = "visibility_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "project_key", "day", name="uq_snapshot_user_project_day"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_key = Column(String(512), nullable=False, index=True)
    day = Column(Date, nullable=False)
    visibility = Column(Float, nullable=False)
    avg_position = Column(Float, nullable=True)
