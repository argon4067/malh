from typing import List, Literal, Optional
from pydantic import BaseModel, Field

JobFamily = Literal[
    "IT", "FINANCE", "MARKETING", "SALES", "DESIGN", "HR",
    "EDUCATION", "HEALTHCARE", "MANUFACTURING", "LOGISTICS",
    "CUSTOMER_SERVICE", "LEGAL", "PUBLIC", "RESEARCH", "ETC"
]

KeywordType = Literal[
    "SKILL", "TOOL", "DOMAIN_TERM", "CERTIFICATE", "ACHIEVEMENT",
    "EDU", "SOFT_SKILL", "TASK", "INDUSTRY", "METRIC", "ETC"
]


class EvidenceItem(BaseModel):
    quote: str = Field(..., description="이력서 원문 근거")
    reason: str = Field(..., description="판단 이유")


class ResumeClassificationResult(BaseModel):
    job_family: JobFamily
    job_role: Optional[str] = Field(default=None, description="예: 백엔드 개발자")
    evidence: List[EvidenceItem] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ResumeKeywordItem(BaseModel):
    keyword: str = Field(..., description="추출 키워드")
    keyword_type: KeywordType = Field(default="ETC")
    evidence: List[EvidenceItem] = Field(default_factory=list)


class ResumeKeywordResult(BaseModel):
    keywords: List[ResumeKeywordItem] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)