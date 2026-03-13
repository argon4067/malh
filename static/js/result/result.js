$(function () {
    function setExpanded($card, expanded) {
        const $toggle = $card.find("[data-toggle-card]");
        const $body = $card.find("[data-expand-body]");
        $toggle.attr("aria-expanded", expanded ? "true" : "false");
        $card.toggleClass("expanded", expanded);
        $body.toggleClass("hidden", !expanded);
    }

    function setCardLoading($card, loading) {
        const $loading = $card.find("[data-card-loading]");
        const $content = $card.find("[data-card-content]");
        $loading.toggleClass("hidden", !loading);
        $content.toggleClass("hidden", loading);
    }

    function buildSpeechFeedbackText(payload) {
        const report = String(payload.report_md || "").trim();
        const coaching = String(payload.coaching_md || "").trim();

        if (report && coaching) {
            return `${report}\n\n${coaching}`;
        }

        return report || coaching || "발화 피드백 결과가 비어 있습니다.";
    }

    async function fetchSpeechFeedback(url, formData, $status, $output) {
        $status.removeClass("ready").text("생성 중");
        $output.text("");

        const response = await fetch(url, {
            method: "POST",
            body: formData,
        });

        const data = await response.json().catch(() => null);
        if (!response.ok) {
            const message = data && data.detail ? data.detail : "발화 피드백 요청이 실패했습니다.";
            throw new Error(message);
        }

        $output.text(buildSpeechFeedbackText(data || {}));
        $status.addClass("ready").text("완료");
    }

    async function runSpeechFeedback($card, force = true) {
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
        setCardLoading($card, true);

        const formData = new FormData();
        formData.append("force", force ? "1" : "0");

        try {
            $status.prop("disabled", true);
            await fetchSpeechFeedback(
                `/interviews/${sessionId}/questions/${selId}/speech-feedback`,
                formData,
                $status,
                $output,
            );
            $card.data("speechLoaded", true);
            $status.prop("disabled", true);
        } catch (error) {
            $status.removeClass("ready").text("오류");
            $output.text(error.message || "발화 피드백 생성에 실패했습니다.");
        } finally {
            setCardLoading($card, false);
            if (!$card.data("speechLoaded")) {
                $status.prop("disabled", false);
            }
            $card.data("speechLoading", false);
        }
    }

    function triggerCardFeedback($card) {
        if (!$card.data("speechLoaded")) {
            void runSpeechFeedback($card, false);
        } else {
            setCardLoading($card, false);
        }
    }

    function bindAccordion() {
        $(".result-card").each(function () {
            const $card = $(this);
            const $toggle = $card.find("[data-toggle-card]");
            $toggle.find("a, button.btn-analysis").on("click", function (e) {
                e.stopPropagation();
            });

            setExpanded($card, false);
            setCardLoading($card, false);

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
