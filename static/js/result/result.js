/**
 * result.js - 결과 목록 아코디언 + 카드 펼침 시 자동 LLM 피드백 생성
 */

$(function () {
    function setExpanded($card, expanded) {
        const $toggle = $card.find("[data-toggle-card]");
        const $body = $card.find("[data-expand-body]");
        $toggle.attr("aria-expanded", expanded ? "true" : "false");
        $card.toggleClass("expanded", expanded);
        $body.toggleClass("hidden", !expanded);
    }

    async function streamToBox(url, formData, $status, $output) {
        $status.removeClass("ready").text("생성 중...");
        $output.text("");

        const response = await fetch(url, {
            method: "POST",
            body: formData,
        });
        if (!response.ok) {
            const text = await response.text();
            throw new Error(text || "피드백 요청에 실패했습니다.");
        }
        if (!response.body) {
            throw new Error("스트리밍 응답을 받을 수 없습니다.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let fullText = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }
            const chunk = decoder.decode(value, { stream: true });
            fullText += chunk;
            $output.text(fullText);
        }

        $status.addClass("ready").text("완료");
    }

    async function runSpeechFeedback($card) {
        const $status = $card.find("[data-speech-status]");
        const $output = $card.find("[data-speech-feedback-output]");
        const selId = Number($card.data("sel-id") || 0);
        const sessionId = Number($status.data("session-id") || 0);
        if (!sessionId || !selId) {
            return;
        }
        if ($card.data("speechLoading")) {
            return;
        }
        $card.data("speechLoading", true);

        const formData = new FormData();
        formData.append("force", "1");

        try {
            await streamToBox(
                `/api/interviews/${sessionId}/questions/${selId}/speech-feedback/stream`,
                formData,
                $status,
                $output,
            );
        } catch (error) {
            $status.removeClass("ready").text("오류");
            $output.text(error.message || "발화 피드백 생성에 실패했습니다.");
        } finally {
            $card.data("speechLoading", false);
        }
    }

    function triggerCardFeedback($card) {
        void runSpeechFeedback($card);
    }

    function bindAccordion() {
        $(".result-card").each(function () {
            const $card = $(this);
            const $toggle = $card.find("[data-toggle-card]");
            $toggle.find("a, button.btn-analysis").on("click", function (e) {
                e.stopPropagation();
            });
            setExpanded($card, false);
            $toggle.on("click", function () {
                const isExpanded = $toggle.attr("aria-expanded") === "true";
                const nextExpanded = !isExpanded;
                setExpanded($card, nextExpanded);
                if (nextExpanded) {
                    triggerCardFeedback($card);
                }
            });
        });
    }

    bindAccordion();
});
