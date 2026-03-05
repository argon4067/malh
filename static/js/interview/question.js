/**
 * question.js - interview question list interactions
 */

const interviewContext = window.INTERVIEW_CONTEXT || {};
const sessionId = Number(interviewContext.sessionId || 0);
const totalQuestionsFromContext = Number(interviewContext.totalQuestions || 0);
const recordedQuestionsFromContext = Number(interviewContext.recordedQuestions || 0);

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

    const totalQuestions = totalQuestionsFromContext || $(".question-list .question-card").length || 0;
    const recordedQuestions = recordedQuestionsFromContext || $(".question-list .q-status.done").length || 0;

    if (totalQuestions !== 5) {
        alert(`면접 질문은 5개여야 제출할 수 있습니다. (현재 ${totalQuestions}개)`);
        return;
    }
    if (recordedQuestions < 5) {
        alert(`5개 질문의 녹음을 모두 완료해 주세요. (${recordedQuestions}/5 완료)`);
        return;
    }

    const $btn = $(".submit-btn");
    $btn.prop("disabled", true).text("분석 중...");

    fetch(`/api/interviews/${sessionId}/submit-analysis/start`, {
        method: "POST",
    })
        .then(async (response) => {
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.detail || "제출 분석에 실패했습니다.");
            }
            location.href = `/interviews/${sessionId}/submit-loading`;
        })
        .catch((error) => {
            alert(error.message || "제출 분석에 실패했습니다.");
        })
        .finally(() => {
            $btn.prop("disabled", false).text("제출하기");
        });
}

$(function () {
    console.log("question list loaded");
});
