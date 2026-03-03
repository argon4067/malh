/**
 * question.js - interview question list interactions
 */

const interviewContext = window.INTERVIEW_CONTEXT || {};
const sessionId = Number(interviewContext.sessionId || 0);

function goToDetail(selId) {
    if (!sessionId || !selId) {
        return;
    }
    location.href = `/interviews/${sessionId}/questions/${selId}`;
}

function submitAnswers() {
    if (!sessionId) {
        return;
    }
    location.href = `/interviews/${sessionId}/results`;
}

$(function () {
    console.log("question list loaded");
});
