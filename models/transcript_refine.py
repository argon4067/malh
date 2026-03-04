from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import text

from .base import Base


class TranscriptRefine(Base):
    __tablename__ = "transcript_refine"

    refine_id = Column(Integer, primary_key=True, autoincrement=True)
    sel_id = Column(Integer, ForeignKey("select_question.sel_id"), nullable=False, unique=True)
    raw_text = Column(Text, nullable=False)
    refined_text = Column(Text, nullable=True)
    edit_log = Column(JSON, nullable=True)
    refine_confidence = Column(Integer, nullable=True, comment="0~100")
    changed_ratio = Column(Integer, nullable=True, comment="0~100")
    status = Column(String(20), nullable=False, server_default=text("'PENDING'"))
    reject_reason = Column(String(255), nullable=True)
    llm_model = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
