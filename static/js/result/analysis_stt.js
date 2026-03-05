/**
 * analysis_stt.js - speech score detail page interactions
 */

$(function () {
    const $btn = $("#generateFeedbackBtn");
    const $status = $("#feedbackStatus");
    const $reportBox = $("#llmReportBox");
    const $coachingBox = $("#llmCoachingBox");
    const $reportContent = $("#llmReportContent");
    const $coachingContent = $("#llmCoachingContent");
    const $helpModal = $("#metricHelpModal");
    const $helpTitle = $("#helpModalTitle");
    const $helpMeaning = $("#helpModalMeaning");
    const $helpCriteria = $("#helpModalCriteria");
    const $helpEvaluation = $("#helpModalEvaluation");
    const $helpAggregation = $("#helpModalAggregation");
    let bodyOriginalOverflow = "";
    let bodyOriginalPaddingRight = "";

    const HELP_CONTENTS = {
        fluency_score: {
            title: "유창성 점수 도움말",
            meaning: "말이 끊기지 않고 자연스럽게 이어지는 정도를 0~100 점수로 나타낸 지표입니다.",
            criteria: [
                "높을수록 말의 흐름이 안정적이고 자연스러운 상태입니다.",
                "낮을수록 속도 불안정, 머뭇거림, 반복 표현이 많을 가능성이 큽니다.",
            ],
            evaluation: "유창성 점수는 말의 속도, 끊김, 반복을 함께 반영한 종합 유창성 지표입니다.",
        },
        clarity_score: {
            title: "명료성 점수 도움말",
            meaning: "발화가 얼마나 또렷하게 인식되고 전달되는지를 0~100 점수로 나타낸 지표입니다.",
            criteria: [
                "높을수록 발화가 선명하고 인식 품질이 안정적인 상태입니다.",
                "낮을수록 발음, 잡음, 전달 명확성 측면의 저하 가능성이 있습니다.",
            ],
            evaluation: "명료성 점수는 인식 안정성과 전사 품질을 함께 반영한 전달 명확성 지표입니다.",
        },
        structure_score: {
            title: "발화 구조 점수 도움말",
            meaning: "문장 구성과 논리 전개의 안정성을 0~100 점수로 나타낸 지표입니다.",
            criteria: [
                "높을수록 문장 길이와 연결 구조가 균형 있게 구성된 상태입니다.",
                "낮을수록 문장 길이 편차가 크거나 연결 구조가 약한 상태일 수 있습니다.",
            ],
            evaluation: "발화 구조 점수는 문장 구성의 균형과 논리적 연결성을 함께 반영합니다.",
        },
        length_score: {
            title: "답변 길이 점수 도움말",
            meaning: "답변 길이가 기준 범위에 맞는지를 0~100 점수로 나타낸 지표입니다.",
            criteria: [
                "높을수록 답변 길이와 분량이 적정 범위에 가까운 상태입니다.",
                "낮을수록 답변이 너무 짧거나 과도하게 긴 상태일 수 있습니다.",
            ],
            evaluation: "답변 길이 점수는 시간과 단어 수 기준에서 적정 길이를 판단하는 지표입니다.",
        },
        delivery_quality: {
            title: "전달 품질 도움말",
            meaning: "유창성과 명료성을 합쳐 실제 전달력을 요약한 품질 지표입니다.",
            criteria: [
                "높을수록 말의 흐름과 명확성이 모두 좋은 상태입니다.",
                "낮을수록 흐름 또는 명확성 중 하나 이상이 약한 상태일 수 있습니다.",
            ],
            evaluation: "전달 품질은 유창성과 명료성을 같은 비중으로 결합한 최종 전달력 지표입니다.",
        },
        content_quality: {
            title: "내용 품질 도움말",
            meaning: "질문 적합도와 정보 구성도를 합쳐 답변 내용의 질을 요약한 지표입니다.",
            criteria: [
                "높을수록 질문과의 관련성, 논리 연결, 정보 밀도가 균형 잡힌 상태입니다.",
                "낮을수록 주제 적합도 또는 내용 구조/밀도가 부족할 수 있습니다.",
            ],
            evaluation: "내용 품질은 관련성, 구조성, 정보 밀도, 주제 커버리지를 함께 평가한 종합 지표입니다.",
        },
        wpm: {
            title: "발화 속도 도움말",
            meaning: "1분 동안 발화된 단어 개수를 나타내는 지표입니다.",
            criteria: [
                "값이 낮을수록 발화 속도가 느린 상태입니다.",
                "값이 높을수록 빠르게 말하는 상태입니다.",
                "과도하게 빠르면 이해도가 저하될 수 있습니다.",
            ],
            evaluation: "적정 발화 속도는 청취자가 내용을 자연스럽게 이해할 수 있는 말하기 흐름을 의미합니다.",
        },
        speed_variation: {
            title: "속도 변동 도움말",
            meaning: "발화 속도가 시간에 따라 얼마나 크게 변하는지를 나타내는 지표입니다.",
            criteria: [
                "값이 낮을수록 속도 변동이 작고 안정적인 상태입니다.",
                "값이 높을수록 말하기 속도의 흔들림이 큰 상태입니다.",
            ],
            evaluation: "속도 변동이 작을수록 안정적인 전달 흐름으로 평가됩니다.",
        },
        filler_frequency: {
            title: "머뭇거림 빈도 도움말",
            meaning: "발화 중 멈춤, 끊김, 망설임이 발생한 횟수와 전체 발화 대비 비율을 나타내는 지표입니다.",
            criteria: [
                "횟수가 많을수록 발화 흐름이 끊기는 상태입니다.",
                "비율이 낮을수록 자연스러운 말하기 상태입니다.",
            ],
            evaluation: "머뭇거림은 사고 정리 지연 또는 발화 준비 부족의 신호로 해석됩니다.",
        },
        repetition_usage: {
            title: "반복어 사용 도움말",
            meaning: "같은 단어나 구문이 반복된 횟수와 전체 발화 대비 비율을 나타내는 지표입니다.",
            criteria: [
                "반복이 많을수록 발화 구조가 불안정한 상태입니다.",
                "반복이 적을수록 명확한 전달 상태입니다.",
            ],
            evaluation: "반복어는 발화 준비 부족 또는 긴장 상태에서 발생하는 대표적 유창성 저해 요소입니다.",
        },
        silence_total: {
            title: "침묵 총합 도움말",
            meaning: "전체 발화 시간 중 침묵 상태가 차지하는 총시간을 나타내는 지표입니다.",
            criteria: [
                "값이 클수록 실제 발화 대비 멈춤 시간이 많은 상태입니다.",
                "값이 작을수록 지속적으로 말한 상태입니다.",
            ],
            evaluation: "침묵 총합은 전체 발화 흐름의 연속성을 평가하는 핵심 지표입니다.",
        },
        pause_segment_length: {
            title: "침묵 구간 길이 도움말",
            meaning: "발화 사이에 발생한 침묵 구간의 평균 길이와 최대 길이를 나타내는 지표입니다.",
            criteria: [
                "평균 길이가 길수록 발화 흐름이 자주 끊기는 상태입니다.",
                "최대 길이가 길수록 장시간 발화 중단이 발생한 상태입니다.",
            ],
            evaluation: "침묵 구간은 사고 정리 시간 또는 발화 준비 부족을 반영하는 지표입니다.",
        },
        stt_accuracy: {
            title: "STT 정확도 도움말",
            meaning: "음성을 텍스트로 변환하는 과정에서 실제 발화 내용이 얼마나 정확하게 인식되었는지를 나타내는 지표입니다.",
            criteria: [
                "값이 높을수록 발화가 또렷하고 명확하게 인식된 상태입니다.",
                "값이 낮을수록 발음 불명확, 잡음, 속도 문제 등이 존재하는 상태입니다.",
            ],
            evaluation: "STT 정확도는 전체 음성 전달 명확성을 판단하는 핵심 지표입니다.",
        },
        avg_stt_confidence: {
            title: "평균 STT 신뢰도 도움말",
            meaning: "STT 엔진이 각 단어 인식 결과에 부여한 신뢰도 값을 평균한 지표입니다.",
            criteria: [
                "값이 높을수록 인식 결과의 안정성이 높은 상태입니다.",
                "값이 낮을수록 발화 품질 또는 음성 환경 문제가 존재하는 상태입니다.",
            ],
            evaluation: "STT 정확도와 함께 음성 인식 품질의 안정성을 평가하는 보조 지표입니다.",
        },
        pronunciation_clarity: {
            title: "발음 분명도 도움말",
            meaning: "각 음절이 얼마나 명확하게 발음되었는지를 나타내는 발음 선명도 지표입니다.",
            criteria: [
                "값이 높을수록 발음이 또렷하고 명확한 상태입니다.",
                "값이 낮을수록 발음이 흐릿하거나 불명확한 상태입니다.",
            ],
            evaluation: "발음 분명도는 청취자가 내용을 정확히 이해할 수 있는 전달력을 나타냅니다.",
        },
        articulation_ratio: {
            title: "조음 비율 도움말",
            meaning: "전체 발화 중 명확하게 발음된 음절의 비율을 나타내는 지표입니다.",
            criteria: [
                "값이 높을수록 또렷한 발화 비중이 높은 상태입니다.",
                "값이 낮을수록 불명확 발음 비중이 높은 상태입니다.",
            ],
            evaluation: "조음 비율은 발화 명료도의 정량적 측정값입니다.",
        },
        volume_stability: {
            title: "음량 안정성 도움말",
            meaning: "발화 중 음량 크기가 얼마나 일정하게 유지되었는지를 나타내는 지표입니다.",
            criteria: [
                "값이 낮을수록 음량 변화가 적어 안정적인 상태입니다.",
                "값이 높을수록 음량 변동이 커 전달 품질이 불안정한 상태입니다.",
            ],
            evaluation: "음량 안정성은 청취 피로도와 전달 명확성에 직접적인 영향을 줍니다.",
        },
        clipping_ratio: {
            title: "클리핑 비율 도움말",
            meaning: "음성 신호가 과도하게 커져 왜곡이 발생한 비율을 나타내는 지표입니다.",
            criteria: [
                "값이 낮을수록 음성 신호가 정상 범위에서 유지된 상태입니다.",
                "값이 높을수록 음성 왜곡이 발생한 상태입니다.",
            ],
            evaluation: "클리핑은 음성 품질 저하의 대표적인 물리적 신호 오류입니다.",
        },
        sentence_length_distribution: {
            title: "문장 길이 분포 도움말",
            meaning: "각 문장의 길이 평균과 문장 간 길이 차이를 나타내는 지표입니다.",
            criteria: [
                "평균 길이는 한 문장에 포함된 정보량 수준을 의미합니다.",
                "변동값은 문장 길이의 균형 정도를 의미합니다.",
                "변동이 낮을수록 문장 길이가 일정한 상태입니다.",
            ],
            evaluation: "문장 길이 분포는 발화 구조의 안정성과 정보 전달 밀도를 판단하는 기준입니다.",
        },
        discourse_segmentation: {
            title: "의미 단위 분절 도움말",
            meaning: "발화 내용이 의미적으로 구분되는 단위의 총개수와 문장당 평균개수를 나타내는 지표입니다.",
            criteria: [
                "총개수가 많을수록 전달된 정보가 다양하고 세분화된 상태입니다.",
                "문장당 개수가 많을수록 하나의 문장에 포함된 의미요소가 많은 상태입니다.",
            ],
            evaluation: "의미 단위 분절은 답변의 정보 구조화 수준을 평가하는 지표입니다.",
        },
        incomplete_unit_ratio: {
            title: "불완전 의미 단위 비율 도움말",
            meaning: "문장 내 의미 전달이 끝까지 완성되지 못한 단위의 비율을 나타내는 지표입니다.",
            criteria: [
                "값이 낮을수록 문장이 완결된 형태로 구성된 상태입니다.",
                "값이 높을수록 의미가 중단되거나 불완전한 발화가 많은 상태입니다.",
            ],
            evaluation: "불완전 단위는 논리적 전달력 저하를 나타내는 구조적 오류 지표입니다.",
        },
        connective_usage: {
            title: "연결어 사용 도움말",
            meaning: "문장 간 또는 문장 내부에서 의미 흐름을 연결하는 단어의 사용비율과 종류수를 나타내는 지표입니다.",
            criteria: [
                "밀도가 높을수록 논리 연결 표현이 풍부한 상태입니다.",
                "종류수가 많을수록 다양한 연결 구조를 사용한 상태입니다.",
            ],
            evaluation: "연결어 사용은 발화의 논리 전개 능력을 평가하는 핵심 구조 지표입니다.",
        },
        sentence_count: {
            title: "문장 수 도움말",
            meaning: "전체 발화에서 생성된 문장의 총개수를 나타내는 지표입니다.",
            criteria: [
                "문장 수가 많을수록 발화가 세분화된 상태입니다.",
                "문장 수가 적을수록 긴 문장 중심의 발화 구조입니다.",
            ],
            evaluation: "문장 수는 발화 구성 방식과 정보 분할 전략을 나타냅니다.",
        },
        units_per_sentence: {
            title: "문장당 의미 단위 도움말",
            meaning: "한 문장에 포함된 평균 의미 단위 수를 나타내는 지표입니다.",
            criteria: [
                "값이 높을수록 문장 내 정보 밀도가 높은 상태입니다.",
                "값이 낮을수록 간결한 문장 중심 구조입니다.",
            ],
            evaluation: "이 지표는 문장의 정보 압축 수준을 평가합니다.",
        },
        length_adequacy: {
            title: "답변 길이 적절성 도움말",
            meaning: "전체 단어 수를 기준 범위와 비교하여 답변 길이의 적정성을 판단하는 지표입니다.",
            criteria: [
                "기준 하한 미만이면 짧은 답변 상태입니다.",
                "기준 상한 초과이면 과도하게 긴 답변 상태입니다.",
                "기준 범위 내이면 적정 길이 상태입니다.",
            ],
            evaluation: "이 지표는 답변의 정보량 적절성을 판단하는 핵심 길이 평가 기준입니다.",
        },
        avg_sentence_length: {
            title: "문장 평균 길이 도움말",
            meaning: "전체 발화에서 문장 하나가 평균적으로 포함하는 단어 수를 나타내는 지표입니다.",
            criteria: [
                "값이 높을수록 긴 문장 중심 발화 구조입니다.",
                "값이 낮을수록 짧고 분절된 문장 구조입니다.",
            ],
            evaluation: "문장 평균 길이는 발화 스타일과 전달 방식의 특징을 나타냅니다.",
        },
    };

    const HELP_AGGREGATIONS = {
        fluency_score: "발화 속도 점수 50% + 머뭇거림 점수 25% + 반복어 점수 25%를 합산해 계산합니다.",
        clarity_score: "전사 일관성(인식 안정성) 70% + 전사 품질(텍스트 청결도) 30%를 합산해 계산합니다.",
        structure_score: "문장 길이 적정성 45% + 길이 변동 안정성 30% + 연결어 밀도 25%를 합산해 계산합니다.",
        length_score: "길이 적정성 점수(시간 기준) 70% + 단어 수 적정성 점수 30%를 합산해 계산합니다.",
        delivery_quality: "유창성 점수 50% + 명료성 점수 50%로 계산합니다.",
        content_quality: "관련성 30% + 연결 구조 30% + 세부 정보성 25% + 주제 커버리지 15%를 합산해 계산합니다.",
        wpm: "총 단어 수를 발화 시간(분)으로 나눠 분당 단어 수로 계산합니다.",
        speed_variation: "문장 길이의 표준편차 값을 그대로 사용합니다.",
        filler_frequency: "머뭇거림 횟수를 전체 단어 수로 나눈 비율을 표시합니다.",
        repetition_usage: "반복어 횟수를 (전체 단어 수 - 1)로 나눈 비율을 표시합니다.",
        silence_total: "전체 시간에서 추정 발화 시간을 뺀 뒤, 0~전체 시간 범위로 보정해 계산합니다.",
        pause_segment_length: "침묵 총합을 (의미 단위 수 - 1, 최소 1)로 나눈 값을 사용하며, 현재 화면은 최대값 기준 프록시를 표시합니다.",
        stt_accuracy: "전사 품질을 기반으로 하고 머뭇거림/반복어 패널티를 반영해 0~1 범위로 보정해 계산합니다.",
        avg_stt_confidence: "STT 정확도에서 0.015를 차감한 뒤 0~1 범위로 보정해 계산합니다.",
        pronunciation_clarity: "전사 품질에서 0.03을 차감한 뒤 0~1 범위로 보정해 계산합니다.",
        articulation_ratio: "전사 품질에 0.02를 더한 뒤 0~1 범위로 보정해 계산합니다.",
        volume_stability: "발화 속도 점수를 기반으로 산출 후 0~4 범위로 보정해 계산합니다.",
        clipping_ratio: "(1 - 전사 품질) 값에 0.02를 곱한 뒤 0~0.02 범위로 보정해 계산합니다.",
        sentence_length_distribution: "문장별 단어 수를 기준으로 표준편차를 계산합니다.",
        discourse_segmentation: "현재 화면에서는 문장 분리 수(문장 수)를 표시합니다.",
        incomplete_unit_ratio: "현재 화면에서는 반복어 비율 값을 재사용해 표시합니다.",
        connective_usage: "연결어 개수를 의미 단위 수로 나눈 밀도로 계산합니다.",
        sentence_count: "전사 텍스트를 문장 단위로 분리한 개수로 계산합니다.",
        units_per_sentence: "문장별 단어 수 합계를 문장 수로 나눈 평균으로 계산합니다.",
        length_adequacy: "답변 시간 기준으로 적정 구간(60~120초) 밴드 점수 방식으로 계산합니다.",
        avg_sentence_length: "문장별 단어 수 합계를 문장 수로 나눈 평균으로 계산합니다.",
    };

    function openHelpModal(key) {
        const help = HELP_CONTENTS[key];
        if (!help) {
            return;
        }
        $helpTitle.text(help.title);
        $helpMeaning.text(help.meaning);
        $helpCriteria.empty();
        help.criteria.forEach((item) => {
            $("<li>").text(item).appendTo($helpCriteria);
        });
        $helpEvaluation.text(help.evaluation);
        $helpAggregation.text(HELP_AGGREGATIONS[key] || "코드 기준 집계 식이 정의되지 않은 항목입니다.");
        $helpModal.removeClass("hidden").attr("aria-hidden", "false");
        const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
        const bodyStyle = document.body.style;
        bodyOriginalOverflow = bodyStyle.overflow;
        bodyOriginalPaddingRight = bodyStyle.paddingRight;
        bodyStyle.overflow = "hidden";
        if (scrollbarWidth > 0) {
            bodyStyle.paddingRight = `${scrollbarWidth}px`;
        }
    }

    function closeHelpModal() {
        $helpModal.addClass("hidden").attr("aria-hidden", "true");
        const bodyStyle = document.body.style;
        bodyStyle.overflow = bodyOriginalOverflow;
        bodyStyle.paddingRight = bodyOriginalPaddingRight;
    }

    async function generateFeedback() {
        const sessionId = Number($btn.data("session-id") || 0);
        const selId = Number($btn.data("sel-id") || 0);
        if (!sessionId || !selId) {
            alert("페이지 정보가 올바르지 않습니다.");
            return;
        }

        $btn.prop("disabled", true).text("LLM 피드백 생성 중...");
        $status.text("발화 지표를 기반으로 분석 리포트와 코칭 피드백을 생성하고 있습니다.");

        const formData = new FormData();
        formData.append("force", "1");

        try {
            const response = await fetch(`/api/interviews/${sessionId}/questions/${selId}/speech-feedback`, {
                method: "POST",
                body: formData,
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.detail || "LLM 피드백 요청에 실패했습니다.");
            }

            $reportContent.text(data.report_md || "");
            $coachingContent.text(data.coaching_md || "");
            $reportBox.removeClass("hidden");
            $coachingBox.removeClass("hidden");
            $status.text("LLM 피드백이 생성되었습니다.");
        } catch (error) {
            $status.text("");
            alert(error.message || "LLM 피드백 생성에 실패했습니다.");
        } finally {
            $btn.prop("disabled", false).text("LLM 피드백 다시 생성");
        }
    }

    if ($btn.length) {
        if ($reportContent.text().trim() || $coachingContent.text().trim()) {
            $btn.text("LLM 피드백 다시 생성");
        }
        $btn.on("click", () => {
            void generateFeedback();
        });
    }

    $(".help-text-trigger, .help-trigger").on("click", function () {
        const key = String($(this).data("help-key") || "");
        openHelpModal(key);
    });

    $helpModal.on("click", "[data-help-close]", closeHelpModal);
    $(document).on("keydown", (event) => {
        if (event.key === "Escape" && !$helpModal.hasClass("hidden")) {
            closeHelpModal();
        }
    });
});

function scrollToTop() {
    $("html, body").animate({ scrollTop: 0 }, 250);
}
