/**
 * answer_analysis.js - answer analysis wait interactions
 */

$(function () {
    let progress = 0;
    const $progressBar = $("#progressBar");
    const $percentageText = $("#percentageText");
    const $statusTitle = $("#statusTitle");
    const $statusDesc = $("#statusDesc");

    const stages = [
        {
            title: "AI가 음성을 분석하고 있습니다...",
            desc: "음성파일을 분석하여 유창성, 명료성 등을 평가하고 있어요",
        },
        {
            title: "AI가 텍스트를 추출하고 있습니다...",
            desc: "음성파일을 분석하여 텍스트를 만들고 있어요",
        },
        {
            title: "AI가 텍스트를 분석하고 있습니다...",
            desc: "텍스트파일을 분석하여 논리와 적합성 등을 평가하고 있어요",
        },
    ];

    function getSessionIdFromPath() {
        const match = window.location.pathname.match(/\/interviews\/(\d+)/);
        return match ? Number(match[1]) : 0;
    }

    function updateStageUI(stageIndex) {
        $(".stage-icon").each(function (idx) {
            $(this).toggleClass("active", idx === stageIndex);
        });

        $statusTitle.text(stages[stageIndex].title);
        $statusDesc.text(stages[stageIndex].desc);

        $(".step-dot").each(function (idx) {
            $(this).toggleClass("active", idx === stageIndex);
        });
    }

    function startSimulation() {
        const interval = setInterval(() => {
            progress += Math.random() * 1.5;
            if (progress > 100) progress = 100;

            $progressBar.css("width", progress + "%");
            $percentageText.text(Math.floor(progress) + "%");

            if (progress < 33) {
                updateStageUI(0);
            } else if (progress < 70) {
                updateStageUI(1);
            } else {
                updateStageUI(2);
            }

            if (progress >= 100) {
                clearInterval(interval);
                setTimeout(() => {
                    const sessionId = getSessionIdFromPath();
                    if (sessionId) {
                        $(location).attr("href", `/interviews/${sessionId}/results`);
                    } else {
                        $(location).attr("href", "/");
                    }
                }, 800);
            }
        }, 50);
    }

    startSimulation();
});
