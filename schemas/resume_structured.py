from typing import List, Optional

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
    position: Optional[str] = None
    career_summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)

    educations: List[EducationItem] = Field(default_factory=list)
    experiences: List[ExperienceItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    certificates: List[CertificateItem] = Field(default_factory=list)