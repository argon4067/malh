/**
 * weakness_wait.js
 * - 시뮬레이션 제거
 * - 실제 약점 보강 질문 생성 API 호출
 * - 생성 완료 후 새 weakness session으로 이동
 */

function getSourceSessionIdFromPath() {
    const match = window.location.pathname.match(/\/interviews\/(\d+)\/weakness\/wait/);
    return match ? Number(match[1]) : 0;
}

$(function () {
    let progress = 0;
    let finished = false;

    const sessionId = getSourceSessionIdFromPath();
    const $progressBar = $("#progressBar");
    const $percentageText = $("#percentageText");

    function updateUI(value) {
        $progressBar.css("width", value + "%");
        $percentageText.text(value + "%");
    }

    function startFakeProgress() {
        return setInterval(() => {
            if (finished) return;
            if (progress >= 90) return;

            const increment = Math.floor(Math.random() * 5) + 3;
            progress = Math.min(90, progress + increment);
            updateUI(progress);
        }, 180);
    }

    async function startGeneration() {
        if (!sessionId) {
            alert("세션 정보가 올바르지 않습니다.");
            window.location.href = "/resumes";
            return;
        }

        const interval = startFakeProgress();

        try {
            const response = await fetch(`/api/interviews/${sessionId}/weakness/start`, {
                method: "POST",
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(data.detail || "약점 보강 질문 생성에 실패했습니다.");
            }

            finished = true;
            progress = 100;
            updateUI(progress);
            clearInterval(interval);

            setTimeout(() => {
                window.location.href = `/interviews/${data.weakness_session_id}/weakness`;
            }, 400);
        } catch (error) {
            finished = true;
            clearInterval(interval);
            alert(error.message || "약점 보강 질문 생성에 실패했습니다.");
            window.location.href = `/interviews/${sessionId}/results`;
        }
    }

    updateUI(0);
    startGeneration();
});