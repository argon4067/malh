/**
 * weakness.js - weakness question list interactions
 */

function getSessionIdFromPath() {
    const match = window.location.pathname.match(/\/interviews\/(\d+)/);
    return match ? Number(match[1]) : 0;
}

function goToWeaknessDetail(id, isRecorded = false) {
    const sessionId = getSessionIdFromPath();
    if (!sessionId || !id) return;
    if (isRecorded) {
        const shouldRerecord = confirm("이미 답변완료 한 질문입니다. 재녹음 하시겠습니까?");
        if (!shouldRerecord) {
            return;
        }
    }
    $(location).attr("href", `/interviews/${sessionId}/weakness/${id}`);
}

function completeReinforcement() {
    const sessionId = getSessionIdFromPath();
    if (!sessionId) return;
    
    $(location).attr("href", `/interviews/${sessionId}/weakness/report-loading`);
    
}
