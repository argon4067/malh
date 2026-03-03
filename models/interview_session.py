from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, DateTime, Enum, ForeignKey
from sqlalchemy.sql import text

from .base import Base


class InterviewSession(Base):
    __tablename__ = "interview_session"

    inter_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resume.resume_id"), nullable=False)
    set_id = Column(Integer, ForeignKey("question_set.set_id"), nullable=False)
    inter_status = Column(Enum("IN_PROGRESS", "DONE"), nullable=False)
    inter_started_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    inter_finished_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="interview_sessions")
    resume = relationship("Resume", back_populates="interview_sessions")
    question_set = relationship("QuestionSet", back_populates="interview_sessions")
    selected_questions = relationship("SelectQuestion", back_populates="interview_session")
