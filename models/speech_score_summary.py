from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, ForeignKey, DECIMAL

from .base import Base


class SpeechScoreSummary(Base):
    __tablename__ = "speech_score_summary"

    score_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="질문 단위 음성 평가 점수 요약 레코드를 유일하게 식별하는 기본키",
    )
    sel_id = Column(Integer, ForeignKey("select_question.sel_id"), nullable=False, unique=True)
    
    sss_fluency_score = Column(
        DECIMAL(5, 2),
        nullable=False,
        comment="발화 속도, 머뭇거림, 반복어, 침묵 구간 등을 종합 평가하여 계산된 유창성 상위 점수",
    )
    sss_clarity_score = Column(
        DECIMAL(5, 2),
        nullable=False,
        comment="STT 정확도, 발음 분명도, 음량 안정성 등을 종합 평가하여 계산된 명료성 상위 점수",
    )
    sss_structure_score = Column(
        DECIMAL(5, 2),
        nullable=False,
        comment="문장 길이 분포, 의미 단위 분절, 연결어 사용 등을 종합 평가하여 계산된 발화 구조 상위 점수",
    )
    sss_length_score = Column(
        DECIMAL(5, 2),
        nullable=False,
        comment="답변 길이 적절성과 발화 시간 기준을 종합 평가하여 계산된 답변 길이 상위 점수",
    )

    select_question = relationship("SelectQuestion", back_populates="speech_summary")
