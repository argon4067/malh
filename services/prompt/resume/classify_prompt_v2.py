PROMPT_VERSION_CLASSIFY = "RESUME_CLASSIFY_V2"

CLASSIFY_SYSTEM_PROMPT = """
당신은 업로드된 문서가 이력서인지 판별하고, 이력서인 경우 직무군(job_family)과 직무명(job_role)을 분류하는 분석기입니다.
반드시 제공된 스키마에 맞는 JSON만 출력하십시오.
스키마에 없는 필드는 출력하지 마십시오.
근거 없는 추측은 금지합니다.
판단이 모호하면 보수적으로 판단하십시오.
"""

def build_classify_user_prompt(resume_text: str) -> str:
    return f"""
아래 문서를 읽고, 이력서 여부를 판단한 뒤 직무군과 직무명을 분류하십시오.

[목표]
- 문서가 이력서이면: job_family, job_role을 분류
- 문서가 이력서가 아니면: 안전하게 "이력서 아님"으로 반환

[규칙]
- job_family는 반드시 아래 값 중 하나만 사용:
  IT, FINANCE, MARKETING, SALES, DESIGN, HR, EDUCATION, HEALTHCARE,
  MANUFACTURING, LOGISTICS, CUSTOMER_SERVICE, LEGAL, PUBLIC, RESEARCH, ETC

- job_role은 가능한 경우 구체적으로 작성:
  예) 백엔드 개발자, 프론트엔드 개발자, 데이터 분석가, 인사 담당자

- evidence에는 반드시 다음 2가지를 포함하십시오:
  1) 원문 근거
  2) 그 근거를 바탕으로 한 판단 이유

- 문서만 보고 판단 가능한 내용만 사용하십시오.
- 추측, 상상, 일반론 보완 금지
- 여러 직무가 섞여 있더라도 가장 핵심적인 직무 1개만 선택하십시오.
- 직무가 불명확하면 job_family는 ETC를 사용하십시오.

[이력서가 아닌 파일 처리 규칙]
아래 중 하나라도 강하게 해당하면 이력서가 아닌 파일로 판단하십시오.
- 경력, 기술, 프로젝트, 학력, 자격 등 이력서 핵심 항목이 거의 없음
- 채용공고, 회사소개서, 기사, 과제설명서, 계약서, 안내문, 공문, 보고서, 포트폴리오 설명문 등에 가까움
- 개인정보 일부만 있고 직무 이력 정보가 없음
- 본문이 너무 짧거나 의미 있는 내용이 거의 없음
- OCR 실패/깨짐 등으로 문서 내용을 해석하기 어려움

이력서가 아닌 파일로 판단한 경우 반드시 다음처럼 반환하십시오.
- is_resume: false
- job_family: "ETC"
- job_role: "이력서 아님"
- evidence: 이력서로 보기 어려운 원문 근거와 이유 작성

이력서로 판단한 경우 반드시 다음처럼 반환하십시오.
- is_resume: true
- job_family: 분류 결과
- job_role: 구체적 직무명
- evidence: 원문 근거와 이유 작성

[문서 원문]
{resume_text}
"""