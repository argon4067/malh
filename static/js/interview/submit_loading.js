const submitLoadingContext = window.SUBMIT_LOADING_CONTEXT || {};
const sessionId = Number(submitLoadingContext.sessionId || 0);

async function pollProgress() {
    if (!sessionId) {
        alert("세션 정보가 올바르지 않습니다.");
        location.href = "/";
        return;
    }

    const $bar = $("#loadingProgressBar");
    const $percent = $("#loadingPercent");
    const $count = $("#loadingCount");
    const $message = $("#loadingMessage");

    const buildProgressMessage = (data) => {
        const total = Number(data.total || 0);
        const completed = Number(data.completed || 0);
        const failedCount = Number(data.failed_count || 0);

        if (data.done) {
            return data.ok
                ? "분석이 완료되었습니다. 결과 화면으로 이동합니다."
                : `분석 중 오류가 발생했습니다. 실패 ${failedCount}건`;
        }

        if (!total) {
            return "분석 준비 중입니다.";
        }

        if (completed <= 0) {
            return "답변 분석을 시작합니다.";
        }

        return `답변 ${completed}/${total} 분석 중입니다.`;
    };

    const tick = async () => {
        try {
            const response = await fetch(`/api/interviews/${sessionId}/submit-analysis/progress`);
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.detail || "진행 조회에 실패했습니다.");
            }
            const data = await response.json();

            const percent = Number(data.percent || 0);
            const total = Number(data.total || 0);
            const completed = Number(data.completed || 0);
            const failedCount = Number(data.failed_count || 0);

            $bar.css("width", `${percent}%`);
            $percent.text(`${percent}%`);
            $count.text(`${completed}/${total}`);
            $message.text(buildProgressMessage(data));

            if (data.done) {
                if (data.ok) {
                    location.href = `/interviews/${sessionId}/results`;
                    return;
                }
                const failedItems = Array.isArray(data.failed) ? data.failed : [];
                const failedQuestions = failedItems
                    .map((item) => Number(item.sel_order_no || 0))
                    .filter((orderNo) => orderNo > 0)
                    .map((orderNo) => `Q${orderNo}`)
                    .join(", ");
                const failureSummary = failedQuestions ? `실패 질문: ${failedQuestions}\n` : "";
                const failureDetails = failedItems.length > 0
                    ? failedItems
                        .map((item) => {
                            const orderNo = Number(item.sel_order_no || 0);
                            const label = orderNo > 0 ? `Q${orderNo}` : "질문 번호 미상";
                            const reason = item.reason || "알 수 없는 오류";
                            return `${label}: ${reason}`;
                        })
                        .join("\n")
                    : "알 수 없는 오류";
                const resetNotice = data.reset_applied
                    ? "\n녹음/분석 상태를 초기화했습니다. 다시 녹음해 주세요."
                    : "";
                alert(
                    `분석 중 실패가 발생했습니다. (${failedCount}건)\n${failureSummary}${failureDetails}${resetNotice}`
                );
                location.href = `/interviews/${sessionId}`;
                return;
            }
        } catch (error) {
            alert(error.message || "진행 상태 확인에 실패했습니다.");
            location.href = `/interviews/${sessionId}`;
            return;
        }

        setTimeout(() => {
            void tick();
        }, 500);
    };

    await tick();
}

$(function () {
    void pollProgress();
});
