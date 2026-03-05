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

    const tick = async () => {
        try {
            const response = await fetch(`/api/interviews/${sessionId}/submit-analysis/progress`);
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.detail || "진행률 조회 실패");
            }
            const data = await response.json();

            const percent = Number(data.percent || 0);
            const total = Number(data.total || 0);
            const completed = Number(data.completed || 0);
            const failedCount = Number(data.failed_count || 0);

            $bar.css("width", `${percent}%`);
            $percent.text(`${percent}%`);
            $count.text(`${completed}/${total}`);
            $message.text(data.message || "분석 중...");

            if (data.done) {
                if (data.ok) {
                    location.href = `/interviews/${sessionId}/results`;
                    return;
                }
                const firstFailed = data.failed && data.failed[0] ? data.failed[0].reason : "알 수 없는 오류";
                alert(`분석 중 실패가 발생했습니다. (${failedCount}건)\n${firstFailed}`);
                location.href = `/interviews/${sessionId}/results`;
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
