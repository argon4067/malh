let timerInterval = null;
let seconds = 0;
let mediaRecorder = null;
let mediaStream = null;
let recordedChunks = [];
let isRecording = false;

const interviewContext = window.INTERVIEW_CONTEXT || {};
const sessionId = Number(interviewContext.sessionId || 0);
const selId = Number(interviewContext.selId || 0);

function startTimer() {
    const $timerElement = $("#timer");
    seconds = 0;
    $timerElement.text("00:00");

    timerInterval = setInterval(() => {
        seconds += 1;
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        $timerElement.text(
            `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`,
        );
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
    const ext = blob.type.includes("mp4") ? "m4a" : "webm";
    const fileName = `answer.${ext}`;
    const file = new File([blob], fileName, { type: blob.type || "audio/webm" });

    const formData = new FormData();
    formData.append("audio_file", file);
    formData.append("duration_sec", String(seconds));

    const response = await fetch(
        `/api/interviews/${sessionId}/questions/${selId}/recordings`,
        {
            method: "POST",
            body: formData,
        },
    );

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const message = data.detail || "Recording upload failed.";
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

async function startRecordingFlow() {
    if (isRecording) {
        return;
    }
    if (!sessionId || !selId) {
        alert("Interview context is invalid.");
        return;
    }
    if (!window.MediaRecorder) {
        alert("This browser does not support audio recording.");
        return;
    }

    try {
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

        mediaRecorder.start();
        isRecording = true;
        $("#mode-standby").removeClass("active");
        $("#mode-recording").addClass("active");
        startTimer();
    } catch (_error) {
        cleanupStream();
        alert("Microphone permission is required.");
    }
}

function finishRecording() {
    if (!isRecording || !mediaRecorder) {
        return;
    }

    isRecording = false;
    stopTimer();

    mediaRecorder.onstop = async () => {
        try {
            const type = mediaRecorder.mimeType || "audio/webm";
            const blob = new Blob(recordedChunks, { type });
            await uploadRecordedAudio(blob);
            alert("Recording saved.");
            window.location.href = `/interviews/${sessionId}`;
        } catch (error) {
            alert(error.message || "Failed to save recording.");
            $("#mode-recording").removeClass("active");
            $("#mode-standby").addClass("active");
        } finally {
            cleanupStream();
            mediaRecorder = null;
            recordedChunks = [];
        }
    };

    mediaRecorder.stop();
}

$(function () {
    console.log("question_detail loaded");
});
