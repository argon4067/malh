from typing import List, Literal

from pydantic import BaseModel, Field


class QuestionCandidateItem(BaseModel):
    category: Literal["TECH", "PROJECT", "BEHAVIOR", "CS", "ETC"]
    difficulty: Literal["EASY", "MEDIUM", "HARD"]
    question_text: str = Field(..., min_length=5, max_length=500)
    evidence: List[str] = Field(default_factory=list)


class QuestionCandidateResult(BaseModel):
    questions: List[QuestionCandidateItem]