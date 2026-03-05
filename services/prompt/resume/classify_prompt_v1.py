# PROMPT_VERSION_CLASSIFY = "RESUME_CLASSIFY_V1"

CLASSIFY_SYSTEM_PROMPT = (
    "당신은 이력서를 직무군으로 분류하는 분석기입니다. "
    "반드시 제공된 스키마에 맞는 JSON만 출력하십시오. "
    "근거 없는 추측은 금지합니다."
)


def build_classify_user_prompt(resume_text: str) -> str:
    return f"""
아래 이력서 텍스트를 읽고 직무군과 직무명을 분류하십시오.

[규칙]
- job_family는 반드시 아래 값 중 하나만 사용:
  IT, FINANCE, MARKETING, SALES, DESIGN, HR, EDUCATION, HEALTHCARE,
  MANUFACTURING, LOGISTICS, CUSTOMER_SERVICE, LEGAL, PUBLIC, RESEARCH, ETC
- job_role은 가능한 경우 구체적으로 작성:
  예) 백엔드 개발자, 프론트엔드 개발자, 데이터 분석가
- evidence에는 반드시 원문 근거와 판단 이유를 넣으십시오.
- 불명확하면 ETC를 사용하십시오.

[이력서 원문]
{resume_text}
"""