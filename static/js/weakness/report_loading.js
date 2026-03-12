const weaknessReportLoadingContext = window.WEAKNESS_REPORT_LOADING_CONTEXT || {};
const sessionId = Number(weaknessReportLoadingContext.sessionId || 0);

async function startWeaknessReportJob() {
    const response = await fetch(`/api/interviews/${sessionId}/weakness/report/start`, {
        method: "POST",
    });

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "개선 추적 리포트 준비를 시작하지 못했습니다.");
    }

    return response.json().catch(() => ({}));
}

async function pollWeaknessReportProgress() {
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
                ? "개선 추적 리포트가 준비되었습니다. 화면으로 이동합니다."
                : `리포트 준비 중 오류가 발생했습니다. 실패 ${failedCount}건`;
        }

        if (!total) {
            return "리포트 준비 중입니다.";
        }

        if (completed <= 0) {
            return "보강 답변 분석을 시작합니다.";
        }

        return `보강 답변 ${completed}/${total} 분석 중입니다.`;
    };

    const tick = async () => {
        try {
            const response = await fetch(`/api/interviews/${sessionId}/weakness/report/progress`);
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
                    location.href = `/interviews/${sessionId}/weakness/report`;
                    return;
                }

                const failedItems = Array.isArray(data.failed) ? data.failed : [];
                const failedQuestions = failedItems
                    .map((item) => Number(item.sel_order_no || 0))
                    .filter((orderNo) => orderNo > 0)
                    .map((orderNo) => `보강 Q${orderNo}`)
                    .join(", ");
                const failureSummary = failedQuestions ? `실패 질문: ${failedQuestions}\n` : "";
                const failureDetails = failedItems.length > 0
                    ? failedItems
                        .map((item) => {
                            const orderNo = Number(item.sel_order_no || 0);
                            const label = orderNo > 0 ? `보강 Q${orderNo}` : "질문 번호 미상";
                            const reason = item.reason || "알 수 없는 오류";
                            return `${label}: ${reason}`;
                        })
                        .join("\n")
                    : "알 수 없는 오류";
                alert(`리포트 준비 중 실패가 발생했습니다. (${failedCount}건)\n${failureSummary}${failureDetails}`);
                location.href = `/interviews/${sessionId}/weakness`;
                return;
            }
        } catch (error) {
            alert(error.message || "진행 상태 확인에 실패했습니다.");
            location.href = `/interviews/${sessionId}/weakness`;
            return;
        }

        setTimeout(() => {
            void tick();
        }, 500);
    };

    await tick();
}

$(function () {
    void startWeaknessReportJob()
        .then(() => pollWeaknessReportProgress())
        .catch((error) => {
            alert(error.message || "개선 추적 리포트 준비를 시작하지 못했습니다.");
            location.href = `/interviews/${sessionId}/weakness`;
        });
});
