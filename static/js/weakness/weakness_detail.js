/**
 * weakness_detail.js - weakness detail recording interactions
 */

let timerInterval = null;
let seconds = 0;

function getSessionIdFromPath() {
    const match = window.location.pathname.match(/\/interviews\/(\d+)/);
    return match ? Number(match[1]) : 0;
}

function startRecordingFlow() {
    if (confirm("마이크 사용 권한을 허용하시겠습니까?")) {
        $("#mode-standby").removeClass("active");
        $("#mode-recording").addClass("active");
        startTimer();
    } else {
        alert("마이크 권한이 필요합니다.");
    }
}

function startTimer() {
    const $timerElement = $("#timer");
    seconds = 0;
    $timerElement.text("00:00");

    timerInterval = setInterval(() => {
        seconds += 1;
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        $timerElement.text(`${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`);
    }, 1000);
}

function finishRecording() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }

    const sessionId = getSessionIdFromPath();
    alert("보강 답변이 저장되었습니다.");
    if (sessionId) {
        $(location).attr("href", `/interviews/${sessionId}/weakness`);
    }
}

$(function () {
    console.log("weakness detail loaded");
});
