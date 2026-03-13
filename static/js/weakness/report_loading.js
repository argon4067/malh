const weaknessReportLoadingContext = window.WEAKNESS_REPORT_LOADING_CONTEXT || {};
const sessionId = Number(weaknessReportLoadingContext.sessionId || 0);

const progressBar = document.getElementById("loadingProgressBar");
const percentText = document.getElementById("loadingPercent");
const countText = document.getElementById("loadingCount");
const messageText = document.getElementById("loadingMessage");

let pollTimer = null;
let isPolling = false;
let targetProgress = 0;
let renderedProgress = 0;
let animationFrameId = null;
let lastFrameTime = 0;
let pendingRedirectUrl = null;
let redirectScheduled = false;
const PROGRESS_SMOOTHING_MS = 900;
const MAX_PROGRESS_PER_SEC = 20;
const PROGRESS_SETTLE_THRESHOLD = 0.02;
const REDIRECT_READY_THRESHOLD = 99.95;
const REDIRECT_DELAY_MS = 320;

function clampProgress(value) {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return 0;
    }

    return Math.min(100, Math.max(0, numericValue));
}

function renderProgress(progress) {
    if (progressBar) {
        progressBar.style.width = `${progress.toFixed(3)}%`;
    }

    if (percentText) {
        percentText.textContent = `${Math.round(progress)}%`;
    }
}

function renderCount(completed, total) {
    if (!countText) {
        return;
    }

    countText.textContent = `${completed}/${total}`;
}

function renderMessage(message) {
    if (!messageText) {
        return;
    }

    messageText.textContent = message;
}

function scheduleRedirectIfReady() {
    if (
        !pendingRedirectUrl ||
        redirectScheduled ||
        renderedProgress < REDIRECT_READY_THRESHOLD
    ) {
        return;
    }

    redirectScheduled = true;
    window.setTimeout(() => {
        location.href = pendingRedirectUrl;
    }, REDIRECT_DELAY_MS);
}

function animateProgress(frameTime) {
    if (!lastFrameTime) {
        lastFrameTime = frameTime;
    }

    const elapsed = Math.min(frameTime - lastFrameTime, 48);
    lastFrameTime = frameTime;

    const delta = targetProgress - renderedProgress;
    if (Math.abs(delta) < PROGRESS_SETTLE_THRESHOLD) {
        renderedProgress = targetProgress;
    } else {
        const easing = 1 - Math.exp(-elapsed / PROGRESS_SMOOTHING_MS);
        const maxStep = (MAX_PROGRESS_PER_SEC * elapsed) / 1000;
        const easedStep = delta * easing;
        const limitedStep =
            Math.sign(easedStep) * Math.min(Math.abs(easedStep), maxStep);
        renderedProgress += limitedStep;
    }

    renderProgress(renderedProgress);
    scheduleRedirectIfReady();

    const shouldContinue =
        Math.abs(targetProgress - renderedProgress) >= PROGRESS_SETTLE_THRESHOLD ||
        (pendingRedirectUrl && renderedProgress < REDIRECT_READY_THRESHOLD);

    if (shouldContinue) {
        animationFrameId = window.requestAnimationFrame(animateProgress);
        return;
    }

    animationFrameId = null;
    lastFrameTime = 0;
}

function ensureProgressAnimation() {
    if (animationFrameId !== null) {
        return;
    }

    animationFrameId = window.requestAnimationFrame(animateProgress);
}

function setProgress(progress) {
    targetProgress = Math.max(targetProgress, clampProgress(progress));
    ensureProgressAnimation();
}

function stopPolling() {
    if (!pollTimer) {
        return;
    }

    window.clearTimeout(pollTimer);
    pollTimer = null;
}

function buildProgressMessage(data) {
    const total = Number(data.total || 0);
    const completed = Number(data.completed || 0);
    const failedCount = Number(data.failed_count || 0);

    if (data.done) {
        return data.ok
            ? "\uAC1C\uC120 \uCD94\uC801 \uB9AC\uD3EC\uD2B8\uAC00 \uC900\uBE44\uB418\uC5C8\uC2B5\uB2C8\uB2E4. \uD654\uBA74\uC73C\uB85C \uC774\uB3D9\uD569\uB2C8\uB2E4."
            : `\uB9AC\uD3EC\uD2B8 \uC900\uBE44 \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4. \uC2E4\uD328 ${failedCount}\uAC74`;
    }

    if (!total) {
        return "\uB9AC\uD3EC\uD2B8 \uC900\uBE44 \uC911\uC785\uB2C8\uB2E4.";
    }

    if (completed <= 0) {
        return "\uBCF4\uAC15 \uB2F5\uBCC0 \uBD84\uC11D\uC744 \uC2DC\uC791\uD569\uB2C8\uB2E4.";
    }

    return `\uBCF4\uAC15 \uB2F5\uBCC0 ${completed}/${total} \uBD84\uC11D \uC911\uC785\uB2C8\uB2E4.`;
}

function formatFailureMessage(data) {
    const failedCount = Number(data.failed_count || 0);
    const failedItems = Array.isArray(data.failed) ? data.failed : [];
    const failedQuestions = failedItems
        .map((item) => Number(item.sel_order_no || 0))
        .filter((orderNo) => orderNo > 0)
        .map((orderNo) => `\uBCF4\uAC15 Q${orderNo}`)
        .join(", ");
    const failureSummary = failedQuestions
        ? `\uC2E4\uD328 \uC9C8\uBB38: ${failedQuestions}\n`
        : "";
    const failureDetails =
        failedItems.length > 0
            ? failedItems
                  .map((item) => {
                      const orderNo = Number(item.sel_order_no || 0);
                      const label =
                          orderNo > 0
                              ? `\uBCF4\uAC15 Q${orderNo}`
                              : "\uC9C8\uBB38 \uBC88\uD638 \uBBF8\uC0C1";
                      const reason =
                          item.reason || "\uC54C \uC218 \uC5C6\uB294 \uC624\uB958";
                      return `${label}: ${reason}`;
                  })
                  .join("\n")
            : "\uC54C \uC218 \uC5C6\uB294 \uC624\uB958";

    return `\uB9AC\uD3EC\uD2B8 \uC900\uBE44 \uC911 \uC2E4\uD328\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4. (${failedCount}\uAC74)\n${failureSummary}${failureDetails}`;
}

async function startWeaknessReportJob() {
    const response = await fetch(`/interviews/${sessionId}/weakness/report/start`, {
        method: "POST",
    });

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
            data.detail ||
                "\uAC1C\uC120 \uCD94\uC801 \uB9AC\uD3EC\uD2B8 \uC900\uBE44\uB97C \uC2DC\uC791\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.",
        );
    }

    return response.json().catch(() => ({}));
}

async function tick() {
    if (isPolling) {
        return;
    }

    isPolling = true;

    try {
        const response = await fetch(`/interviews/${sessionId}/weakness/report/progress`);
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(
                data.detail ||
                    "\uC9C4\uD589 \uC870\uD68C\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.",
            );
        }

        const data = await response.json();
        const percent = Number(data.percent || 0);
        const total = Number(data.total || 0);
        const completed = Number(data.completed || 0);

        setProgress(percent);
        renderCount(completed, total);
        renderMessage(buildProgressMessage(data));

        if (data.done) {
            stopPolling();

            if (data.ok) {
                pendingRedirectUrl = `/interviews/${sessionId}/weakness/report`;
                setProgress(100);
                return;
            }

            window.alert(formatFailureMessage(data));
            location.href = `/interviews/${sessionId}/weakness`;
            return;
        }
    } catch (error) {
        stopPolling();
        window.alert(
            error.message ||
                "\uC9C4\uD589 \uC0C1\uD0DC \uD655\uC778\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.",
        );
        location.href = `/interviews/${sessionId}/weakness`;
        return;
    } finally {
        isPolling = false;
    }

    pollTimer = window.setTimeout(() => {
        void tick();
    }, 500);
}

async function pollWeaknessReportProgress() {
    if (!sessionId) {
        window.alert("\uC138\uC158 \uC815\uBCF4\uAC00 \uC62C\uBC14\uB974\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.");
        location.href = "/";
        return;
    }

    if (progressBar) {
        progressBar.style.transition = "none";
    }

    renderCount(0, 0);
    renderMessage("\uC791\uC5C5\uC744 \uC2DC\uC791\uD569\uB2C8\uB2E4.");
    setProgress(0);

    await startWeaknessReportJob();
    await tick();
}

$(function () {
    void pollWeaknessReportProgress().catch((error) => {
        stopPolling();
        window.alert(
            error.message ||
                "\uAC1C\uC120 \uCD94\uC801 \uB9AC\uD3EC\uD2B8 \uC900\uBE44\uB97C \uC2DC\uC791\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.",
        );
        location.href = `/interviews/${sessionId}/weakness`;
    });
});
