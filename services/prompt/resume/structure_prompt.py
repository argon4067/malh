PROMPT_VERSION_STRUCTURE = "RESUME_STRUCTURE_V2"

STRUCTURE_SYSTEM_PROMPT = """
당신은 이력서 구조화 분석기입니다.
반드시 제공된 스키마에 맞는 JSON만 출력하십시오.
문서에 없는 정보는 추측하지 마십시오.
값이 없으면 단일 값은 null, 목록은 []로 반환하십시오.
"""
def build_structure_user_prompt(
    resume_text: str,
    job_family: str | None = None,
    job_role: str | None = None,
) -> str:
    return f"""
아래 이력서 텍스트를 읽고 구조화된 정보를 추출하십시오.

[전제]
- 이 입력은 이미 이력서로 판정된 문서입니다.
- 원문에 없는 내용을 보완하거나 상상하지 마십시오.
- 애매하면 보수적으로 비워 두십시오.

[목표]
다음 필드를 추출하십시오.

1) 개요 탭용
- position
- career_summary
- skills

2) 내용 탭용
- educations
- experiences
- projects
- certificates

[공통 규칙]
- 문서에 직접 드러난 정보만 사용하십시오.
- 없으면 단일 값은 null, 목록은 []로 반환하십시오.
- 날짜 형식은 원문을 최대한 유지하십시오.
  예: 2019.03 / 2025-02 / 2023.01 ~ 2024.06
- description은 길게 쓰지 말고 핵심만 요약하십시오.
- 같은 항목을 과도하게 잘게 쪼개지 마십시오.
- job_family / job_role은 문맥 보조용이며, 원문보다 우선하지 않습니다.

[field별 규칙]
- position:
  문서에서 드러나는 지원 직무, 현재 직무, 희망 직무 중 가장 대표적인 표현
  없으면 null

- career_summary:
  전체 경력 수준을 30자 이내로 간단히 요약
  예: 신입 / 1년 6개월 / 총 3년 / 마케팅 인턴 6개월
  명확하지 않으면 null

- skills:
  기술 스택뿐 아니라 직무 관련 도구/방법론/업무 도구도 포함 가능
  단, 문서에 직접 나온 것만 넣으십시오

- educations:
  학교/기관, 전공/과정, 기간, 상태 등을 가능한 범위에서 묶어서 추출

- experiences:
  회사/기관/조직 단위의 경력, 인턴, 활동, 실무 경험을 추출
  단순 자기소개 문장은 넣지 마십시오

- projects:
  프로젝트명, 기간, 역할, 설명을 가능한 범위에서 추출
  단순 과목명/섹션명은 프로젝트로 만들지 마십시오

- certificates:
  자격증, 면허, 시험 합격, 공식 인증 등을 추출

[참고 직무 정보]
- job_family: {job_family or "UNKNOWN"}
- job_role: {job_role or "UNKNOWN"}

[이력서 원문]
{resume_text}
"""