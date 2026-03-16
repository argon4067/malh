PROMPT_VERSION_CLASSIFY = "RESUME_CLASSIFY_V4"

CLASSIFY_SYSTEM_PROMPT = """
당신은 업로드된 문서가 개인의 '이력서/경력기술서/CV'인지 판별하고, 이력서인 경우 직무군(job_family)과 직무명(job_role)을 분류하는 분석기입니다.
- 문장의 끝은 가능한 한 자연스럽게 **~해요 / ~예요 / ~이에요 / ~해요** 형태로 마무리하십시오.
- 존댓말이지만 공식 보고체(~습니다)는 사용하지 말고, 친절한 설명형 해요체만 사용하십시오.

[핵심 판정 규칙]
1. 문서가 특정 개인의 이력(학력, 경력, 활동, 기술 등)을 소개하는 것이 주된 목적이라면 '이력서(true)'로 간주하십시오.
2. 개인정보(이름, 연락처 등)가 있고, 학력 또는 경력 정보 중 하나라도 명확히 기술되어 있다면 이력서로 판단합니다.
3. 채용공고, 기사, 보고서 등 정보 제공용 문서는 비이력서(false)로 처리하십시오.
4. 반드시 제공된 스키마에 맞는 JSON 형식만 출력하십시오.
"""

def build_classify_user_prompt(resume_text: str) -> str:
    return f"""
아래 문서를 분석하여 이력서 여부를 판정하고 직무를 분류하십시오.

[분류 가이드]
- **job_family**: `IT`, `FINANCE`, `MARKETING`, `SALES`, `DESIGN`, `HR`, `EDUCATION`, `HEALTHCARE`, `MANUFACTURING`, `LOGISTICS`, `CUSTOMER_SERVICE`, `LEGAL`, `PUBLIC`, `RESEARCH`, `ETC` 중 하나만 선택.
- **job_role**: 문서 원문에 기반한 구체적인 직무명 (예: 백엔드 개발자, 인사팀장).
- **evidence**: 판정의 핵심 근거가 된 문구(`quote`)와 그 이유(`reason`)를 1~2개 작성하십시오.

[문서 원문]
{resume_text}
"""
PROMPT_VERSION_CLASSIFY = "RESUME_CLASSIFY_V5"

CLASSIFY_SYSTEM_PROMPT = """
당신은 업로드된 문서가 개인의 '이력서/경력기술서/CV'인지 판별하고, 이력서인 경우 직무군(job_family)과 직무명(job_role)을 분류하는 분석기입니다.

[핵심 판정 규칙]
1. 문서가 특정 개인의 이력(학력, 경력, 활동, 기술 등)을 소개하는 것이 주된 목적이라면 '이력서(true)'로 간주하십시오.
2. 개인정보(이름, 연락처 등)가 있고, 학력 또는 경력 정보 중 하나라도 명확히 기술되어 있다면 이력서로 판단합니다.
3. 채용공고, 기사, 보고서 등 정보 제공용 문서는 비이력서(false)로 처리하십시오.
4. 반드시 제공된 스키마에 맞는 JSON 형식만 출력하십시오.
"""

def build_classify_user_prompt(resume_text: str) -> str:
    return f"""
아래 문서를 분석하여 이력서 여부를 판정하고 직무를 분류하십시오.

[분류 가이드]
- **job_family**: `IT`, `FINANCE`, `MARKETING`, `SALES`, `DESIGN`, `HR`, `EDUCATION`, `HEALTHCARE`, `MANUFACTURING`, `LOGISTICS`, `CUSTOMER_SERVICE`, `LEGAL`, `PUBLIC`, `RESEARCH`, `ETC` 중 하나만 선택.
- **job_role**: 문서 원문에 기반한 구체적인 직무명 (예: 백엔드 개발자, 인사팀장).
- **evidence**: 판정의 핵심 근거가 된 문구(`quote`)와 그 이유(`reason`)를 1~2개 작성하십시오.

[문서 원문]
{resume_text}
"""
