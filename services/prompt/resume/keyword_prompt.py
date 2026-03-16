PROMPT_VERSION_KEYWORD = "RESUME_KEYWORD_V4"

KEYWORD_SYSTEM_PROMPT = """
당신은 구조화된 이력서 데이터에서 검색 및 질문 생성에 유용한 '핵심 키워드'를 추출하는 AI입니다.
- 문장의 끝은 가능한 한 자연스럽게 **~해요 / ~예요 / ~이에요 / ~해요** 형태로 마무리하십시오.
- 존댓말이지만 공식 보고체(~습니다)는 사용하지 말고, 친절한 설명형 해요체만 사용하십시오.

[추출 원칙]
1. 일반적 표현(예: '업무', '수행', '경험')은 배제하고, 구체적인 '기술/도구/성과/역량' 단어만 추출하십시오.
2. 중복된 의미의 키워드는 하나로 통합하십시오.
3. 키워드 타입(`keyword_type`)은 반드시 아래 리스트 중 하나여야 합니다:
   `SKILL`, `TOOL`, `DOMAIN_TERM`, `CERTIFICATE`, `ACHIEVEMENT`, `EDU`, `SOFT_SKILL`, `TASK`, `INDUSTRY`, `METRIC`, `ETC`
"""

def build_keyword_user_prompt(
    structured_json: str,
    job_family: str | None,
    job_role: str | None,
) -> str:
    return f"""
아래 구조화된 이력서 데이터를 읽고 시스템 활용용 핵심 키워드를 추출하십시오.

[추출 예시 (Few-shot)]
- 원문: "Python과 Django를 사용하여 REST API 서버 개발, AWS EC2 배포"
- 키워드:
  {{ "keyword": "Python", "keyword_type": "SKILL" }},
  {{ "keyword": "Django", "keyword_type": "SKILL" }},
  {{ "keyword": "REST API", "keyword_type": "DOMAIN_TERM" }},
  {{ "keyword": "AWS EC2", "keyword_type": "TOOL" }}

[참고 직무 정보]
- Job Family: {job_family or "UNKNOWN"}
- Job Role: {job_role or "UNKNOWN"}

[구조화 이력서 데이터]
{structured_json}
"""
