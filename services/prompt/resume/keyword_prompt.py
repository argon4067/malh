PROMPT_VERSION_KEYWORD = "RESUME_KEYWORD_V1"

KEYWORD_SYSTEM_PROMPT = (
    "당신은 이력서를 직무 기준으로 분석해 핵심 키워드를 추출하는 분석기입니다. "
    "반드시 제공된 스키마에 맞는 JSON만 출력하십시오. "
    "원문 근거가 있는 정보만 사용하십시오."
)


def build_keyword_user_prompt(
    resume_text: str,
    job_family: str,
    job_role: str | None,
) -> str:
    return f"""
아래 이력서를 이미 분류된 직무 기준으로 분석하여 키워드를 추출하십시오.

[분류 결과]
- job_family: {job_family}
- job_role: {job_role or ""}

[키워드 타입]
SKILL, TOOL, DOMAIN_TERM, CERTIFICATE, ACHIEVEMENT, EDU, SOFT_SKILL, TASK, INDUSTRY, METRIC, ETC

[규칙]
- 해당 직무에서 의미 있는 키워드만 추출
- 너무 일반적인 표현은 제외
- 중복 키워드는 제거
- evidence에는 반드시 원문 근거와 판단 이유 포함

[이력서 원문]
{resume_text}
"""