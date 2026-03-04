from datetime import datetime

from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.sql import text

from .base import Base


class LlmRun(Base):
    __tablename__ = "llm_run"

    llm_id = Column(Integer, primary_key=True, autoincrement=True)
    llm_stage = Column(
        String(50),
        nullable=False,
        comment="RESUME_CLASSIFY, RESUME_KEYWORD, INTERVIEW_ANALYZE, QUESTION_GENERATE ...",
    )
    llm_model = Column(String(100), nullable=False, comment="gpt-4o ...")
    llm_prompt_version = Column(String(50), nullable=False, comment="RESUME_CLASSIFY_V1")
    llm_status = Column(Enum("SUCCESS", "FAILED"), nullable=False)
    error_code = Column(String(50), nullable=True, comment="RATE_LIMIT ...")
    error_message = Column(
        String(255),
        nullable=True,
        comment="Rate limit exceeded. Please retry later...",
    )
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    resume_keywords = relationship("ResumeKeyword", back_populates="llm_run")
    resume_classifications = relationship("ResumeClassification", back_populates="llm_run")
    resume_structureds = relationship("ResumeStructured", back_populates="llm_run")
