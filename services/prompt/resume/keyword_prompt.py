PROMPT_VERSION_KEYWORD = "RESUME_KEYWORD_V3"

KEYWORD_SYSTEM_PROMPT = """
당신은 구조화된 이력서 데이터를 기반으로 질문 생성과 검색에 유용한 핵심 키워드를 추출하는 분석기입니다.
반드시 제공된 스키마에 맞는 JSON만 출력하십시오.
문서에 없는 정보를 추측하지 마십시오.
중복 키워드와 유사 중복 키워드는 제거하십시오.
"""
def build_keyword_user_prompt(
    structured_json: str,
    job_family: str | None,
    job_role: str | None,
) -> str:
    return f"""
아래 구조화된 이력서 데이터를 읽고, 시스템 활용용 핵심 키워드를 추출하십시오.

[목표]
- 질문 생성, 검색, 태깅에 유용한 핵심 키워드를 추출
- 상세 소개문이 아니라 검색/분류용 태그를 만든다고 생각하십시오

[반드시 지킬 규칙]
- keyword는 짧고 명확해야 합니다.
- 문서에 직접 나온 정보만 사용하십시오.
- 문서에 없는 기술, 역할, 성과를 추측하지 마십시오.
- 같은 의미의 중복 키워드는 하나만 남기십시오.
- 너무 일반적인 단어는 제외하십시오.
  예: "업무", "경험", "참여", "수행", "프로젝트 경험", "역량" 같은 포괄어
- 섹션 제목만 반복한 키워드는 피하십시오.
  예: "학력", "경력", "프로젝트", "자격증"

[keyword_type 규칙]
반드시 아래 값 중 하나만 사용:
SKILL, TOOL, DOMAIN_TERM, CERTIFICATE, ACHIEVEMENT, EDU, SOFT_SKILL, TASK, INDUSTRY, METRIC, ETC

[evidence 규칙]
- 각 keyword에는 반드시 근거를 넣으십시오.
- evidence.quote는 구조화 데이터 또는 원문 정보에서 확인 가능한 내용만 써야 합니다.
- evidence.reason은 왜 이 키워드가 유효한지 설명하십시오.

[추출 우선순위]
1. 직무 관련 핵심 기술/도구/도메인 용어
2. 구체적인 업무 내용
3. 자격/학력/성과/지표
4. 검색과 질문 생성에 실제로 도움이 되는 용어

[참고 직무 정보]
- job_family: {job_family or "UNKNOWN"}
- job_role: {job_role or "UNKNOWN"}

[구조화 이력서 데이터]
{structured_json}
"""