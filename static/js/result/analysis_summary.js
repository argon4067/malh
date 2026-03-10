$(function () {
    const $btn = $("#runSpeechFeedbackBtn");
    const $output = $("#speechFeedbackOutput");

    async function runSpeechFeedbackStream() {
        const sessionId = Number($btn.data("session-id") || 0);
        const selId = Number($btn.data("sel-id") || 0);
        if (!sessionId || !selId) {
            alert("페이지 정보가 올바르지 않습니다.");
            return;
        }

        $btn.prop("disabled", true).text("생성 중...");
        $output.text("");

        const formData = new FormData();
        formData.append("force", "1");

        try {
            const response = await fetch(`/api/interviews/${sessionId}/questions/${selId}/speech-feedback/stream`, {
                method: "POST",
                body: formData,
            });
            if (!response.ok) {
                const text = await response.text();
                throw new Error(text || "발화 피드백 생성 요청에 실패했습니다.");
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

            $btn.text("다시 생성");
        } catch (error) {
            $output.text("");
            alert(error.message || "발화 피드백 생성에 실패했습니다.");
            $btn.text("데이터 준비됨");
        } finally {
            $btn.prop("disabled", false);
        }
    }

    if ($btn.length && !$btn.prop("disabled")) {
        $btn.on("click", () => {
            void runSpeechFeedbackStream();
        });
    }
});
