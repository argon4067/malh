/**
 * text.js - 텍스트 보기 플레이바/문장 이동 로직
 */

$(function () {
    const $audioPlayer = $(".audio-player");
    const $playBtn = $("#playBtn");
    const $progressFill = $("#progressFill");
    const $progressHead = $("#progressHead");
    const $timeDisplay = $("#timeDisplay");
    const $progressContainer = $("#progressContainer");
    const $scriptContent = $("#scriptContent");
    const audioEl = document.getElementById("answerAudio");

    const durationFromServer = Math.max(0, Number($audioPlayer.data("duration")) || 0);
    const rawText = ($scriptContent.text() || "").trim();

    let currentTime = 0;
    let simulatedDuration = durationFromServer;
    let isPlayingFallback = false;
    let fallbackInterval = null;
    let sentenceTimeline = [];

    function hasRealAudio() {
        return Boolean(audioEl);
    }

    function getTotalDuration() {
        if (hasRealAudio() && Number.isFinite(audioEl.duration) && audioEl.duration > 0) {
            return audioEl.duration;
        }
        if (durationFromServer > 0) {
            return durationFromServer;
        }
        if (simulatedDuration > 0) {
            return simulatedDuration;
        }
        return Math.max(1, sentenceTimeline.length);
    }

    function formatTime(seconds) {
        const safeSec = Math.max(0, Math.floor(seconds));
        const min = Math.floor(safeSec / 60);
        const sec = safeSec % 60;
        return `${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
    }

    function splitSentences(text) {
        const normalized = text.replace(/\s+/g, " ").trim();
        if (!normalized) {
            return [];
        }
        const matches = normalized.match(/[^.!?。！？]+[.!?。！？]?/g) || [];
        const items = matches.map((s) => s.trim()).filter(Boolean);
        return items.length > 0 ? items : [normalized];
    }

    function buildTimeline(sentences, durationSec) {
        if (sentences.length === 0) {
            return [];
        }
        const safeDuration = durationSec > 0 ? durationSec : Math.max(1, sentences.length);
        const weights = sentences.map((s) => Math.max(1, s.replace(/\s/g, "").length));
        const totalWeight = weights.reduce((acc, v) => acc + v, 0);

        let elapsed = 0;
        return sentences.map((text, idx) => {
            const start = elapsed;
            elapsed += (weights[idx] / totalWeight) * safeDuration;
            return { text, start };
        });
    }

    function renderSentences(timeline) {
        if (timeline.length === 0) {
            $scriptContent.text("전사 텍스트가 없습니다.");
            return;
        }
        const html = timeline
            .map((item) => {
                const escapedText = $("<div>").text(item.text).html();
                return `<span class="script-sentence" data-start="${item.start.toFixed(3)}">${escapedText}</span>`;
            })
            .join(" ");
        $scriptContent.html(html);
    }

    function findActiveSentenceIndex() {
        if (sentenceTimeline.length === 0) {
            return -1;
        }
        for (let i = sentenceTimeline.length - 1; i >= 0; i -= 1) {
            if (currentTime >= sentenceTimeline[i].start) {
                return i;
            }
        }
        return 0;
    }

    function updateHighlight() {
        const $sentences = $(".script-sentence");
        $sentences.removeClass("active");
        const activeIdx = findActiveSentenceIndex();
        if (activeIdx >= 0) {
            $sentences.eq(activeIdx).addClass("active");
        }
    }

    function updateUI() {
        const total = getTotalDuration();
        const percent = Math.min(100, Math.max(0, (currentTime / total) * 100));

        $progressFill.css("width", `${percent}%`);
        $progressHead.css("left", `${percent}%`);
        $timeDisplay.text(`${formatTime(currentTime)} / ${formatTime(total)}`);
        updateHighlight();
    }

    function setPlayButtonPlaying(isPlaying) {
        $playBtn.text(isPlaying ? "||" : "▶");
    }

    function stopFallbackPlayer() {
        isPlayingFallback = false;
        if (fallbackInterval) {
            clearInterval(fallbackInterval);
            fallbackInterval = null;
        }
        setPlayButtonPlaying(false);
    }

    function startFallbackPlayer() {
        const total = getTotalDuration();
        if (total <= 0 || sentenceTimeline.length === 0) {
            return;
        }
        isPlayingFallback = true;
        setPlayButtonPlaying(true);
        fallbackInterval = setInterval(() => {
            currentTime += 0.1;
            if (currentTime >= total) {
                currentTime = total;
                stopFallbackPlayer();
            }
            updateUI();
        }, 100);
    }

    function seekTo(seconds) {
        const total = getTotalDuration();
        const clamped = Math.min(Math.max(0, seconds), total);
        currentTime = clamped;

        if (hasRealAudio()) {
            audioEl.currentTime = clamped;
        }
        updateUI();
    }

    function togglePlayback() {
        if (hasRealAudio()) {
            if (audioEl.paused) {
                audioEl.play().catch(() => {
                    setPlayButtonPlaying(false);
                });
            } else {
                audioEl.pause();
            }
            return;
        }

        if (isPlayingFallback) {
            stopFallbackPlayer();
        } else {
            startFallbackPlayer();
        }
    }

    function bindEvents() {
        $playBtn.on("click", togglePlayback);

        $progressContainer.on("click", function (e) {
            const width = $(this).width();
            if (!width) {
                return;
            }
            const clickX = e.offsetX;
            seekTo((clickX / width) * getTotalDuration());
        });

        $scriptContent.on("click", ".script-sentence", function () {
            const start = Number($(this).data("start")) || 0;
            seekTo(start);

            if (hasRealAudio()) {
                audioEl.play().catch(() => {
                    setPlayButtonPlaying(false);
                });
            } else if (!isPlayingFallback) {
                startFallbackPlayer();
            }
        });

        if (hasRealAudio()) {
            audioEl.addEventListener("loadedmetadata", () => {
                if (audioEl.duration > 0) {
                    simulatedDuration = audioEl.duration;
                    sentenceTimeline = buildTimeline(splitSentences(rawText), simulatedDuration);
                    renderSentences(sentenceTimeline);
                }
                updateUI();
            });

            audioEl.addEventListener("timeupdate", () => {
                currentTime = audioEl.currentTime || 0;
                updateUI();
            });

            audioEl.addEventListener("play", () => setPlayButtonPlaying(true));
            audioEl.addEventListener("pause", () => setPlayButtonPlaying(false));
            audioEl.addEventListener("ended", () => setPlayButtonPlaying(false));
            audioEl.addEventListener("error", () => {
                setPlayButtonPlaying(false);
            });
        }
    }

    sentenceTimeline = buildTimeline(splitSentences(rawText), getTotalDuration());
    renderSentences(sentenceTimeline);
    bindEvents();
    updateUI();
});

