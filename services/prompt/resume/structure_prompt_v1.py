PROMPT_VERSION_STRUCTURE = "RESUME_STRUCTURE_V1"

STRUCTURE_SYSTEM_PROMPT = (
    "당신은 이력서 구조화 분석기입니다. "
    "반드시 제공된 스키마에 맞는 JSON만 출력하십시오. "
    "문서에 없는 정보는 추측하지 마십시오."
)


def build_structure_user_prompt(
    resume_text: str,
    job_family: str | None = None,
    job_role: str | None = None,
) -> str:
    return f"""
아래 이력서 텍스트를 읽고 구조화된 정보를 추출하십시오.

[목표]
- 개요 탭용 정보
  - position
  - career_summary
  - skills
- 내용 탭용 정보
  - educations
  - experiences
  - projects
  - certificates

[규칙]
- 문서에 직접 드러난 정보만 사용하십시오.
- 추측 금지
- 없으면 단일 값은 null, 목록은 [] 로 반환하십시오.
- 날짜 형식은 원문을 최대한 유지하십시오. 예: 2019.03, 2025-02, 2023.01 ~ 2024.06
- skills에는 기술 스택, 언어, 프레임워크, DB, 인프라, 주요 도구를 넣으십시오.
- educations / experiences / projects / certificates 는 각각 의미 단위별로 묶어서 반환하십시오.
- description은 너무 길지 않게 핵심만 요약하십시오.
- job_family / job_role 정보는 문맥 보조용이며, 원문보다 우선하지 않습니다.
- career_summary는 30자 이내로 간단히 작성하십시오. 예: 신입, 1년 6개월, 총 3년, 백엔드 개발 2년

[참고 직무 정보]
- job_family: {job_family or "UNKNOWN"}
- job_role: {job_role or "UNKNOWN"}

[이력서 원문]
{resume_text}
"""