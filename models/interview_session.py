from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, DateTime, Enum, ForeignKey
from sqlalchemy.sql import text

from .base import Base


class InterviewSession(Base):
    __tablename__ = "interview_session"

    inter_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    resume_id = Column(
        Integer,
        ForeignKey("resume.resume_id", ondelete="CASCADE"),
        nullable=False,
    )

    set_id = Column(
        Integer,
        ForeignKey("question_set.set_id", ondelete="CASCADE"),
        nullable=False,
    )

    source_inter_id = Column(
        Integer,
        ForeignKey("interview_session.inter_id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        comment="WEAKNESS 세션이 어떤 원본 면접 세션에서 생성되었는지",
    )

    inter_status = Column(Enum("IN_PROGRESS", "DONE"), nullable=False)
    inter_started_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    inter_finished_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="interview_sessions")
    resume = relationship("Resume", back_populates="interview_sessions")
    question_set = relationship("QuestionSet", back_populates="interview_sessions")
    selected_questions = relationship(
        "SelectQuestion",
        back_populates="interview_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    source_session = relationship(
        "InterviewSession",
        remote_side=[inter_id],
        foreign_keys=[source_inter_id],
        back_populates="reinforcement_session",
    )
    reinforcement_session = relationship(
        "InterviewSession",
        foreign_keys=[source_inter_id],
        back_populates="source_session",
        uselist=False,
    )

    
