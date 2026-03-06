/**
 * 이력서 분석 시작 함수 (기존 구조 유지)
 */
function startAnalysis() {
    const resumeSelect = document.getElementById("resumeSelect");
    const selectedResumeId = resumeSelect.value; 
    const companyUrl = document.getElementById("companyUrl").value;
    const companyStack = document.getElementById("companyStack").value;

    if (!selectedResumeId || !companyUrl.trim() || !companyStack.trim()) {
        alert("모든 정보를 입력해주세요.");
        return;
    }

    document.getElementById("inputForm").style.display = "none";
    document.getElementById("loadingArea").style.display = "block";
    document.getElementById("resultArea").style.display = "none";

    fetch('/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            resume_id: parseInt(selectedResumeId),
            company_url: companyUrl,
            companyStack: companyStack
        })
    })
    .then(response => response.json())
    .then(data => {
        renderFeedbackResult(data);
        document.getElementById("loadingArea").style.display = "none";
        document.getElementById("resultArea").style.display = "block";
    })
    .catch(error => {
        alert("분석 중 오류 발생: " + error.message);
        document.getElementById("loadingArea").style.display = "none";
        document.getElementById("inputForm").style.display = "block";
    });
}

/**
 * 분석 결과 데이터를 화면에 주입하는 함수 (순차 검증 및 부분 일치 로직 적용)
 */
/**
 * 분석 결과 데이터를 화면에 주입하는 함수
 */
function renderFeedbackResult(data) {
    const strengthsContent = document.getElementById('strengthsContent');
    const improvementsContent = document.getElementById('improvementsContent');
    const compatibilityWarning = document.getElementById('compatibilityWarning');
    const warningText = document.getElementById('warningText');

    // 이전 결과 및 경고창 초기화
    strengthsContent.innerHTML = '';
    improvementsContent.innerHTML = '';
    if (compatibilityWarning) {
        compatibilityWarning.style.display = 'none';
        compatibilityWarning.style.backgroundColor = '#fff3cd'; // 기본 노란색
        compatibilityWarning.style.color = '#856404';
    }

    // [STEP 1] 이력서 vs 회사 방향성 체크
    if (data.step1_ok === false) {
        if (compatibilityWarning) {
            compatibilityWarning.style.display = 'block';
            warningText.innerText = "[직무 부적합] " + (data.mismatch_reason || "이력서와 회사의 직무 방향이 일치하지 않습니다.");
        }
        strengthsContent.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">직무 전문 분야가 달라 분석을 진행할 수 없습니다.</p>';
        return; // ❌ 분석 중단
    }

    // [STEP 2] 기술 스택 유효성 체크 (하나라도 맞으면 true로 옴)
    if (data.step2_ok === false) {
        if (compatibilityWarning) {
            compatibilityWarning.style.display = 'block';
            compatibilityWarning.style.backgroundColor = '#f8d7da'; // 입력 에러는 빨간색
            compatibilityWarning.style.color = '#721c24';
            warningText.innerText = "[기술 스택 오류] " + (data.mismatch_reason || "유효한 기술 키워드가 없습니다.");
        }
        strengthsContent.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">입력하신 기술 스택이 해당 직무와 관련이 없습니다.</p>';
        return; // ❌ 분석 중단
    }

    // [STEP 3] 정상 결과 렌더링
    if (data.strengths && data.strengths.length > 0) {
        data.strengths.forEach(item => {
            strengthsContent.innerHTML += `
                <div class="result-item" style="margin-top: 10px; border-bottom: 1px dashed #eee; padding-bottom: 10px;">
                    <p style="font-weight: bold; color: #2c3e50;">• ${item.title}</p>
                    <p style="font-size: 0.9em; color: #666; margin-left: 10px;">${item.description}</p>
                </div>`;
        });
    }

    if (data.improvements && data.improvements.length > 0) {
        data.improvements.forEach(item => {
            improvementsContent.innerHTML += `
                <div class="result-item" style="margin-top: 10px; border-bottom: 1px dashed #eee; padding-bottom: 10px;">
                    <p style="font-weight: bold; color: #e67e22;">• ${item.title}</p>
                    <p style="font-size: 0.9em; color: #666; margin-left: 10px;">${item.description}</p>
                </div>`;
        });
    }
}