PROMPT_VERSION_STRUCTURE = "RESUME_STRUCTURE_V6"

STRUCTURE_SYSTEM_PROMPT = """
당신은 이력서 원문에서 정보를 추출하여 JSON으로 구조화하는 데이터 추출 전문가입니다. 
문서의 내용을 최대한 손실 없이, 지정된 스키마에 맞춰 정확하게 변환하십시오.
- 문장의 끝은 가능한 한 자연스럽게 **~해요 / ~예요 / ~이에요 / ~해요** 형태로 마무리하십시오.
- 존댓말이지만 공식 보고체(~습니다)는 사용하지 말고, 친절한 설명형 해요체만 사용하십시오.
"""

def build_structure_user_prompt(
    resume_text: str,
    job_family: str | None = None,
    job_role: str | None = None,
) -> str:
    return f"""
아래 이력서 텍스트를 구조화된 JSON 데이터로 변환하십시오.

[추출 가이드 및 예시 (Few-shot)]

1. **career_summary**: 반드시 '신입' 또는 'N년' 형식으로만 반환. 
   - 예: 1년 2개월 실무 -> "1년", 인턴 6개월 -> "신입", 총 경력 5년 -> "5년"

2. **experiences (경력 및 경험)**:
   - **experience_type**: `FULL_TIME`(정규직), `CONTRACT`(계약직), `PART_TIME`(알바), `INTERN`(인턴), `MILITARY`(군복무), `ETC`(대외활동) 중 선택.
   - **count_as_career (경력 산정 여부)**:
     - `true`: `FULL_TIME` 또는 `CONTRACT` 형태의 실무 경력일 경우.
     - `false`: 인턴(`INTERN`), 아르바이트(`PART_TIME`), 군 복무(`MILITARY`), 교육 수료 등일 경우.
   - *예시*: "A사 백엔드 개발자 (정규직) 2020.01~2022.01" -> type: FULL_TIME, count_as_career: true

3. **projects**: 프로젝트 내 사용 기술을 `technologies` 배열에 추출하십시오.

4. **educations**: 정규 학력(고교, 대학, 대학원)만 추출. 그 외 교육은 제외.

[추출 예시 JSON 구조]
{{
  "position": "백엔드 개발자",
  "career_summary": "2년",
  "skills": ["Python", "Django", "PostgreSQL"],
  "experiences": [
    {{
      "company": "가나다테크",
      "role": "백엔드 엔지니어",
      "start_date": "2020.01",
      "end_date": "2022.01",
      "description": "API 서버 개발 및 유지보수",
      "experience_type": "FULL_TIME",
      "count_as_career": true
    }}
  ],
  ... (나머지 필드 생략)
}}

[이력서 원문]
{resume_text}
"""
