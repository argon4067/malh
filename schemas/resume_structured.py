from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class EducationItem(BaseModel):
    school: str
    major: Optional[str] = None
    degree: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class ExperienceItem(BaseModel):
    company: str
    role: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    experience_type: Optional[
        Literal["FULL_TIME", "CONTRACT", "PART_TIME", "INTERN", "MILITARY", "ETC"]
    ] = None
    count_as_career: bool = False

class ProjectItem(BaseModel):
    name: str
    role: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)




class CertificateItem(BaseModel):
    name: str
    issuer: Optional[str] = None
    acquired_date: Optional[str] = None


class ResumeStructuredResult(BaseModel):
    position: Optional[str] = Field(
        default=None,
        description="대표 직무명",
    )
    career_summary: Optional[str] = Field(
        default=None,
        description="경력 수준/기간 요약값만 허용. 예: 신입, 인턴 3개월, 1년 6개월, 총 3년",
    )
    skills: List[str] = Field(default_factory=list)

    educations: List[EducationItem] = Field(default_factory=list)
    experiences: List[ExperienceItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    certificates: List[CertificateItem] = Field(default_factory=list)