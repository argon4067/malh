function startAnalysis() {
    const resumeSelect = document.getElementById("resumeSelect");
    const selectedResumeId = resumeSelect.value;
    
    if (!selectedResumeId) {
        alert("분석할 이력서가 없습니다. 이력서 등록 페이지로 이동합니다.");
        window.location.href = "/resumes"; 
        return;
    }

    const companyUrl = document.getElementById("companyUrl").value;
    
    document.getElementById("inputForm").style.display = "none";
    document.getElementById("loadingArea").style.display = "block";
    document.getElementById("resultArea").style.display = "none";

    /* 나중에 실제 API 연동 시 사용할 코드
    fetch('/api/feedback/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            resume_id: selectedResumeId,
            company_url: companyUrl
        })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById("loadingArea").style.display = "none";
        document.getElementById("resultArea").style.display = "block";
    })
    .catch(error => {
        alert("분석 중 오류가 발생했습니다.");
        console.error(error);
        document.getElementById("loadingArea").style.display = "none";
        document.getElementById("inputForm").style.display = "block";
    });
    */

    // 임시 UI 테스트용 타이머
    setTimeout(() => {
        document.getElementById("loadingArea").style.display = "none";
        document.getElementById("resultArea").style.display = "block";
    }, 2000);
}