from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import text

from .base import Base


class ResumeStructured(Base):
    __tablename__ = "resume_structured"

    structured_id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resume.resume_id"), nullable=False, unique=True)
    llm_id = Column(Integer, ForeignKey("llm_run.llm_id"), nullable=False)

    structured_position = Column(String(255), nullable=True, comment="백엔드 개발자, AI 개발자 등")
    structured_career_summary = Column(String(255), nullable=True, comment="신입, 3년, 1년 6개월 등")

    structured_skills = Column(JSON, nullable=True, comment="기술 목록")
    structured_educations = Column(JSON, nullable=True, comment="학력 목록")
    structured_experiences = Column(JSON, nullable=True, comment="경력사항 목록")
    structured_projects = Column(JSON, nullable=True, comment="프로젝트 목록")
    structured_certificates = Column(JSON, nullable=True, comment="자격증 목록")

    structured_created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    resume = relationship("Resume", back_populates="structured")
    llm_run = relationship("LlmRun", back_populates="resume_structureds")