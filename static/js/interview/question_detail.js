let timerInterval = null;
let seconds = 0;
let mediaRecorder = null;
let mediaStream = null;
let recordedChunks = [];
let isRecording = false;
let isPreparing = false;
let isPreviewRunning = false;
let questionPreviewUsedCount = 0;
let audioContext = null;
let analyserNode = null;
let sourceNode = null;
let animationFrameId = null;
let frequencyData = null;
let smoothedLevels = [];

const QUESTION_PREVIEW_SECONDS = 5;
const QUESTION_PREVIEW_MAX_COUNT = 2;

function getSessionId() {
    const match = window.location.pathname.match(/\/interviews\/(\d+)/);
    if (match) {
        return Number(match[1]);
    }

    const interviewContext = window.INTERVIEW_CONTEXT || {};
    return Number(interviewContext.sessionId || 0);
}

function getQuestionId() {
    const match = window.location.pathname.match(/\/questions\/(\d+)/);
    if (match) {
        return Number(match[1]);
    }

    const interviewContext = window.INTERVIEW_CONTEXT || {};
    return Number(interviewContext.selId || 0);
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function setStandbyMessage(message) {
    $("#record-guide").text(message);
}

function remainingPreviewCount() {
    return Math.max(0, QUESTION_PREVIEW_MAX_COUNT - questionPreviewUsedCount);
}

function updatePreviewStatusUI() {
    const usedText = `질문 미리보기 사용: ${questionPreviewUsedCount}/${QUESTION_PREVIEW_MAX_COUNT} (각 5초)`;
    $("#standby-placeholder").text(usedText);

    const remain = remainingPreviewCount();
    const recordingText = remain > 0
        ? `녹음 중 질문 다시보기 가능: ${remain}회 남음`
        : "질문 다시보기 사용 횟수를 모두 사용했습니다.";
    $("#recording-placeholder").text(recordingText);

    const exhausted = remain === 0;
    $("#review-question-btn").prop("disabled", exhausted);
    if (exhausted && !$("#recording-preview-countdown").text().trim()) {
        $("#recording-preview-countdown").text("질문 다시보기 2회를 모두 사용했습니다.");
    }
}

async function runQuestionPreview(targetMode) {
    if (isPreviewRunning || remainingPreviewCount() === 0) {
        return false;
    }

    isPreviewRunning = true;
    const isRecordingMode = targetMode === "recording";
    const $text = isRecordingMode ? $("#recording-question-text") : $("#standby-question-text");
    const $placeholder = isRecordingMode ? $("#recording-placeholder") : $("#standby-placeholder");
    const $countdown = isRecordingMode ? $("#recording-preview-countdown") : $("#preview-countdown");

    $placeholder.hide();
    $text.removeClass("hidden");

    for (let remain = QUESTION_PREVIEW_SECONDS; remain > 0; remain -= 1) {
        $countdown.text(`질문 확인 ${remain}초`);
        await sleep(1000);
    }

    $text.addClass("hidden");
    $placeholder.show();
    questionPreviewUsedCount += 1;
    updatePreviewStatusUI();

    if (isRecordingMode) {
        $countdown.text("질문을 다시 숨깁니다.");
        await sleep(300);
        if (remainingPreviewCount() > 0) {
            $countdown.text("");
        }
    } else {
        $countdown.text("녹음을 시작합니다...");
        await sleep(250);
    }

    isPreviewRunning = false;
    return true;
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

function stopTimer() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
}

function pickSupportedMimeType() {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
    for (const mimeType of candidates) {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported(mimeType)) {
            return mimeType;
        }
    }
    return "";
}

async function uploadRecordedAudio(blob) {
    const sessionId = getSessionId();
    const selId = getQuestionId();
    const ext = blob.type.includes("mp4") ? "m4a" : "webm";
    const fileName = `answer.${ext}`;
    const file = new File([blob], fileName, { type: blob.type || "audio/webm" });

    const formData = new FormData();
    formData.append("audio_file", file);
    formData.append("duration_sec", String(seconds));

    const response = await fetch(`/interviews/${sessionId}/questions/${selId}/recordings`, {
        method: "POST",
        body: formData,
    });

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const message = data.detail || "녹음 파일 업로드에 실패했습니다.";
        throw new Error(message);
    }

    return response.json();
}

function cleanupStream() {
    if (mediaStream) {
        mediaStream.getTracks().forEach((track) => track.stop());
        mediaStream = null;
    }
}

function stopVisualizer() {
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
    if (sourceNode) {
        sourceNode.disconnect();
        sourceNode = null;
    }
    if (analyserNode) {
        analyserNode.disconnect();
        analyserNode = null;
    }
    if (audioContext) {
        audioContext.close().catch(() => {});
        audioContext = null;
    }
    frequencyData = null;
    smoothedLevels = [];

    $(".recording-visual .wave-bar").css({
        height: "16px",
        opacity: "0.45",
    });
}

function startVisualizer(stream) {
    const bars = $(".recording-visual .wave-bar").toArray();
    if (!bars.length) {
        return;
    }

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
        return;
    }

    audioContext = new AudioContextClass();
    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 256;
    analyserNode.smoothingTimeConstant = 0.75;
    sourceNode = audioContext.createMediaStreamSource(stream);
    sourceNode.connect(analyserNode);

    frequencyData = new Uint8Array(analyserNode.frequencyBinCount);
    smoothedLevels = Array.from({ length: bars.length }, () => 0);

    const minHeight = 12;
    const maxHeight = 96;
    const binSize = Math.max(1, Math.floor(frequencyData.length / bars.length));

    const render = () => {
        if (!analyserNode) {
            return;
        }
        analyserNode.getByteFrequencyData(frequencyData);

        for (let i = 0; i < bars.length; i += 1) {
            let sum = 0;
            const start = i * binSize;
            const end = Math.min(frequencyData.length, start + binSize);
            for (let j = start; j < end; j += 1) {
                sum += frequencyData[j];
            }
            const avg = sum / Math.max(1, end - start);
            const normalized = avg / 255;

            smoothedLevels[i] = smoothedLevels[i] * 0.6 + normalized * 0.4;
            const height = minHeight + smoothedLevels[i] * (maxHeight - minHeight);
            bars[i].style.height = `${Math.round(height)}px`;
            bars[i].style.opacity = `${Math.max(0.45, Math.min(1, 0.5 + smoothedLevels[i] * 0.8))}`;
        }

        animationFrameId = requestAnimationFrame(render);
    };

    render();
}

async function startInterviewFlow() {
    const sessionId = getSessionId();
    const selId = getQuestionId();

    if (isRecording || isPreparing) {
        return;
    }
    if (!sessionId || !selId) {
        alert("면접 정보가 올바르지 않습니다.");
        return;
    }
    if (!window.MediaRecorder) {
        alert("이 브라우저에서는 음성 녹음을 지원하지 않습니다.");
        return;
    }

    isPreparing = true;
    $("#start-interview-btn").prop("disabled", true);

    try {
        setStandbyMessage("마이크 권한을 확인하는 중입니다.");
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recordedChunks = [];

        const mimeType = pickSupportedMimeType();
        mediaRecorder = mimeType
            ? new MediaRecorder(mediaStream, { mimeType })
            : new MediaRecorder(mediaStream);

        mediaRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
                recordedChunks.push(event.data);
            }
        };

        if (remainingPreviewCount() > 0) {
            setStandbyMessage("질문을 확인하세요.");
            await runQuestionPreview("standby");
        } else {
            $("#preview-countdown").text("질문 미리보기 2회를 모두 사용했습니다.");
            await sleep(500);
        }

        startVisualizer(mediaStream);
        mediaRecorder.start();
        isRecording = true;

        $("#mode-standby").removeClass("active");
        $("#mode-recording").addClass("active");
        $("#preview-countdown").text("");
        startTimer();
        updatePreviewStatusUI();
    } catch (_error) {
        stopVisualizer();
        cleanupStream();
        mediaRecorder = null;
        alert("마이크 권한이 필요합니다.");
        setStandbyMessage("시작 시 질문을 5초 보여준 뒤 녹음이 시작됩니다.");
        $("#preview-countdown").text("");
    } finally {
        isPreparing = false;
        $("#start-interview-btn").prop("disabled", false);
    }
}

async function reviewQuestionDuringRecording() {
    if (!isRecording || isPreviewRunning) {
        return;
    }

    if (remainingPreviewCount() === 0) {
        $("#recording-preview-countdown").text("질문 다시보기 2회를 모두 사용했습니다.");
        return;
    }

    await runQuestionPreview("recording");
}

function startRecordingFlow() {
    return startInterviewFlow();
}

function finishRecording() {
    const sessionId = getSessionId();

    if (!isRecording || !mediaRecorder) {
        return;
    }

    isRecording = false;
    stopTimer();
    stopVisualizer();

    mediaRecorder.onstop = async () => {
        try {
            const type = mediaRecorder.mimeType || "audio/webm";
            const blob = new Blob(recordedChunks, { type });
            await uploadRecordedAudio(blob);
            alert("녹음이 저장되었습니다.");
            window.location.href = `/interviews/${sessionId}`;
        } catch (error) {
            alert(error.message || "녹음 저장에 실패했습니다.");
            $("#mode-recording").removeClass("active");
            $("#mode-standby").addClass("active");
            $("#preview-countdown").text("");
        } finally {
            cleanupStream();
            mediaRecorder = null;
            recordedChunks = [];
        }
    };

    mediaRecorder.stop();
}

$(function () {
    updatePreviewStatusUI();
});
