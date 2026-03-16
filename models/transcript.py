from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, Text, ForeignKey

from .base import Base


class Transcript(Base):
    __tablename__ = "transcript"

    transcript_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="STT 처리로 생성된 전사 텍스트 레코드를 유일하게 식별하는 기본키",
    )
    sel_id = Column(
        Integer,
        ForeignKey("select_question.sel_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    transcript_text = Column(
        Text,
        nullable=False,
        comment="STT 엔진이 음성 답변을 텍스트로 변환한 전체 전사 원문 데이터",
    )

    select_question = relationship("SelectQuestion", back_populates="transcript")
