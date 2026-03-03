from sqlalchemy import BigInteger, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.sql import text

from .base import Base


class AudioRecording(Base):
    __tablename__ = "audio_recording"

    recording_id = Column(BigInteger, primary_key=True, autoincrement=True)
    inter_id = Column(Integer, ForeignKey("interview_session.inter_id"), nullable=False)
    sel_id = Column(Integer, ForeignKey("select_question.sel_id"), nullable=False)
    file_path = Column(String(1024), nullable=False)
    mime_type = Column(String(100), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    duration_sec = Column(Integer, nullable=False, server_default=text("0"))
    upload_status = Column(
        Enum("UPLOADED", "STT_DONE", "FAILED"),
        nullable=False,
        server_default=text("'UPLOADED'"),
    )
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
