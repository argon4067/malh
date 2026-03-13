const progressBar = document.getElementById("progressBar");
const percentageText = document.getElementById("percentageText");
const statusText = document.getElementById("statusText");

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

const STATUS_LABEL_MAP = {
    UPLOADED: "\uBD84\uC11D \uC900\uBE44 \uC911\uC785\uB2C8\uB2E4.",
    CLASSIFYING: "\uC774\uB825\uC11C \uC9C1\uBB34 \uBD84\uB958 \uC911\uC785\uB2C8\uB2E4...",
    STRUCTURING: "\uC774\uB825\uC11C \uAD6C\uC870\uD654 \uBD84\uC11D \uC911\uC785\uB2C8\uB2E4...",
    KEYWORDS_EXTRACTING: "\uD575\uC2EC \uD0A4\uC6CC\uB4DC \uCD94\uCD9C \uC911\uC785\uB2C8\uB2E4...",
    KEYWORDS_DONE: "\uC774\uB825\uC11C \uBD84\uC11D\uC774 \uC644\uB8CC\uB418\uC5C8\uC2B5\uB2C8\uB2E4. \uC9C8\uBB38 \uC0DD\uC131 \uC900\uBE44 \uC911\uC785\uB2C8\uB2E4...",
    QUESTION_GENERATING: "\uBA74\uC811 \uC9C8\uBB38 \uC0DD\uC131 \uC911\uC785\uB2C8\uB2E4...",
    DONE: "\uBAA8\uB4E0 \uC791\uC5C5\uC774 \uC644\uB8CC\uB418\uC5C8\uC2B5\uB2C8\uB2E4.",
    FAILED: "\uCC98\uB9AC \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4.",
};

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

    if (percentageText) {
        percentageText.textContent = `${Math.round(progress)}%`;
    }
}

function renderStatus(status) {
    if (!statusText) {
        return;
    }

    statusText.textContent =
        STATUS_LABEL_MAP[status] || "\uCC98\uB9AC \uC911\uC785\uB2C8\uB2E4...";
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

function updateUI(progress, status) {
    targetProgress = Math.max(targetProgress, clampProgress(progress));
    renderStatus(status);
    ensureProgressAnimation();
}

async function startAnalysis(resumeId, model) {
    const formData = new FormData();
    formData.append("model", model);

    const response = await fetch(`/resumes/${resumeId}/analyze/start`, {
        method: "POST",
        body: formData,
    });

    let result = null;
    try {
        result = await response.json();
    } catch (error) {
        result = null;
    }

    if (!response.ok) {
        const message =
            result && result.detail
                ? result.detail
                : "\uBD84\uC11D \uC2DC\uC791 \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4.";
        throw new Error(message);
    }

    return result;
}

async function fetchStatus(resumeId) {
    const response = await fetch(`/resumes/${resumeId}/status`);

    let result = null;
    try {
        result = await response.json();
    } catch (error) {
        result = null;
    }

    if (!response.ok) {
        const message =
            result && result.detail
                ? result.detail
                : "\uC0C1\uD0DC \uC870\uD68C \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4.";
        throw new Error(message);
    }

    return result;
}

function stopPolling() {
    if (!pollTimer) {
        return;
    }

    window.clearInterval(pollTimer);
    pollTimer = null;
}

async function pollOnce(resumeId) {
    if (isPolling) {
        return;
    }

    isPolling = true;

    try {
        const statusResult = await fetchStatus(resumeId);
        const progress = Number(statusResult.progress || 0);
        const status = statusResult.status || "UPLOADED";

        updateUI(progress, status);

        if (status === "DONE") {
            stopPolling();
            pendingRedirectUrl = statusResult.detail_url || `/resumes/${resumeId}`;
            updateUI(100, "DONE");
            return;
        }

        if (status === "FAILED") {
            stopPolling();
            updateUI(100, "FAILED");
            window.alert(
                statusResult.error_message ||
                    "\uC774\uB825\uC11C \uBD84\uC11D \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4.",
            );
            location.href = "/resumes";
        }
    } finally {
        isPolling = false;
    }
}

async function runAnalysis() {
    const root = document.getElementById("resumeWaitPage");
    if (!root) {
        window.alert("\uD398\uC774\uC9C0 \uC124\uC815\uAC12\uC744 \uCC3E\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.");
        location.href = "/resumes";
        return;
    }

    const resumeId = root.dataset.resumeId;
    const model = root.dataset.model || "gpt-4o-mini";

    if (!resumeId) {
        window.alert("resume_id\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.");
        location.href = "/resumes";
        return;
    }

    if (progressBar) {
        progressBar.style.transition = "none";
    }

    try {
        updateUI(0, "UPLOADED");

        await startAnalysis(resumeId, model);

        await pollOnce(resumeId);

        pollTimer = window.setInterval(() => {
            pollOnce(resumeId).catch((error) => {
                stopPolling();
                window.alert(
                    error.message ||
                        "\uC0C1\uD0DC \uD655\uC778 \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4.",
                );
                location.href = "/resumes";
            });
        }, 900);
    } catch (error) {
        stopPolling();
        window.alert(
            error.message ||
                "\uBD84\uC11D \uCC98\uB9AC \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4.",
        );
        location.href = "/resumes";
    }
}

window.addEventListener("load", runAnalysis);
