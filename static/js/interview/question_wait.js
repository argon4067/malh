/**
 * question_wait.js - question generation wait interactions
 */

$(document).ready(function () {
    let progress = 0;
    const $progressBar = $("#progressBar");
    const $percentageText = $("#percentageText");
    let retryCount = 0;

    function getSessionIdFromPath() {
        const match = window.location.pathname.match(/\/interviews\/(\d+)/);
        return match ? Number(match[1]) : 0;
    }

    function simulateGeneration() {
        const interval = setInterval(() => {
            const increment = Math.floor(Math.random() * 8) + 1;
            progress += increment;

            if (progress >= 100) {
                progress = 100;
                clearInterval(interval);
                updateUI(progress);

                setTimeout(() => {
                    const sessionId = getSessionIdFromPath();
                    if (sessionId) {
                        location.href = `/interviews/${sessionId}`;
                    } else {
                        location.href = "/";
                    }
                }, 500);
            } else {
                updateUI(progress);
            }
        }, 200);
    }

    function updateUI(value) {
        $progressBar.css("width", value + "%");
        $percentageText.text(value + "%");
    }

    function handleError() {
        if (retryCount < 1) {
            retryCount += 1;
            progress = 0;
            simulateGeneration();
        } else {
            location.href = "/";
        }
    }

    simulateGeneration();
});
