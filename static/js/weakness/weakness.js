/**
 * weakness.js - weakness question list interactions
 */

function getSessionIdFromPath() {
    const match = window.location.pathname.match(/\/interviews\/(\d+)/);
    return match ? Number(match[1]) : 0;
}

function goToWeaknessDetail(id) {
    const sessionId = getSessionIdFromPath();
    if (!sessionId || !id) return;
    $(location).attr("href", `/interviews/${sessionId}/weakness/${id}`);
}

function completeReinforcement() {
    const sessionId = getSessionIdFromPath();
    if (!sessionId) return;
    if (confirm("모든 보강 연습을 마치고 최종 결과를 확인하시겠습니까?")) {
        $(location).attr("href", `/interviews/${sessionId}/results`);
    }
}

$(function () {
    console.log("weakness list loaded");
});
