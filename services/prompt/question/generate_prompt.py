from typing import Optional

PROMPT_VERSION_QUESTION_GENERATE = "QUESTION_GENERATE_V1"

QUESTION_GENERATE_SYSTEM_PROMPT = (
    "당신은 이력서 기반 모의면접 질문 생성기입니다. "
    "반드시 제공된 스키마에 맞는 JSON만 출력하십시오. "
    "근거 없는 추측은 금지합니다."
)


def build_question_generate_user_prompt(
    structured_json: str,
    job_family: Optional[str],
    job_role: Optional[str],
    purpose: str,
    count: int,
    existing_questions_text: str = "",
) -> str:
    return f"""
아래 이력서 구조화 JSON을 바탕으로 모의면접 질문 {count}개를 생성하십시오.

[질문 목적]
- purpose: {purpose}

[직무 정보]
- job_family: {job_family or "UNKNOWN"}
- job_role: {job_role or "UNKNOWN"}

[규칙]
- 반드시 questions 배열 형태의 JSON만 출력하십시오.
- category는 반드시 아래 값 중 하나만 사용:
  TECH, PROJECT, BEHAVIOR, CS, ETC
- difficulty는 반드시 아래 값 중 하나만 사용:
  EASY, MEDIUM, HARD
- question_text는 자연스러운 한국어 면접 질문 1문장으로 작성하십시오.
- evidence는 반드시 원문 구조화 데이터에 근거한 문자열 배열로 넣으십시오.
- 근거 없는 질문은 금지합니다.
- 너무 짧거나 애매한 질문은 금지합니다.
- 예/아니오로 끝나는 단답형 질문은 지양하십시오.
- 프로젝트 경험이 있다면 PROJECT 질문을 충분히 포함하십시오.
- 이미 생성된 질문과 의미가 겹치는 질문은 피하십시오.

[이미 생성된 질문 목록]
{existing_questions_text or "없음"}

[이력서 구조화 JSON]
{structured_json}
""".strip()