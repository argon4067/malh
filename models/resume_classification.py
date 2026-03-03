from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, JSON
from sqlalchemy.sql import text

from .base import Base


class ResumeClassification(Base):
    __tablename__ = "resume_classification"

    class_id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resume.resume_id"), nullable=False, unique=True)
    llm_id = Column(Integer, ForeignKey("llm_run.llm_id"), nullable=False)
    class_job_family = Column(
        Enum(
            "IT","FINANCE","MARKETING","SALES","DESIGN","HR","EDUCATION","HEALTHCARE","MANUFACTURING","LOGISTICS",
            "CUSTOMER_SERVICE","LEGAL","PUBLIC","RESEARCH","ETC"
        ),
        nullable=False,
    )
    class_job_role = Column(String(255), nullable=True, comment="백엔드, 프론트, 서버...")
    class_evidence = Column(JSON, nullable=False)
    class_created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    resume = relationship("Resume", back_populates="classification")
    llm_run = relationship("LlmRun", back_populates="resume_classifications")
