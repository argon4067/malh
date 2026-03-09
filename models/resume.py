from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, CHAR
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import text

from .base import Base


class Resume(Base):
    __tablename__ = "resume"

    resume_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    resume_file_name = Column(String(100), nullable=False)
    resume_file_type = Column(Enum("DOCX", "PDF"), nullable=False)
    resume_file_path = Column(String(255), nullable=True)
    resume_file_size = Column(Integer, nullable=True, comment="단위: byte")
    resume_extracted_text = Column(LONGTEXT, nullable=True)
    resume_sha256 = Column(CHAR(64), nullable=False)
    resume_created_at = Column(
        DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP")
    )
    resume_updated_at = Column(
        DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP")
    )
    resume_status = Column(
        Enum("UPLOADED",
    "CLASSIFYING",
    "STRUCTURING",
    "KEYWORDS_EXTRACTING",
    "KEYWORDS_DONE",
    "QUESTION_GENERATING",
    "DONE",
    "FAILED"), nullable=False, server_default="UPLOADED")
    resume_error_message = Column(String(255), nullable=True)
    
    user = relationship("User", back_populates="resumes")
    keywords = relationship(
        "ResumeKeyword",
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    classification = relationship(
        "ResumeClassification",
        back_populates="resume",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    structured = relationship(
        "ResumeStructured",
        back_populates="resume",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    question_sets = relationship(
        "QuestionSet",
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    interview_sessions = relationship(
        "InterviewSession",
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
