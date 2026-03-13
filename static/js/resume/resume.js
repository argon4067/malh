/**
 * resume.js - 이력서 관리 화면 전환, 업로드, 카드 슬라이더 로직
 */

$(function () {
    // 1. 화면 요소 참조
    const $dashboardView = $('#dashboard-view');
    const $uploadView = $('#upload-view');
    const $dropZone = $('#dropZone');
    const $fileInput = $('#fileInput');

    const $resumeList = $('#resume-list');
    const $prevBtn = $('#resumePrevBtn');
    const $nextBtn = $('#resumeNextBtn');

    // 서버로 보낼 값
    const model = $('#modelInput').val() || 'gpt-4o-mini';

    let currentIndex = 0;

    // 2. 화면 전환 이벤트

    // 업로드 제한값 상수화
    const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
    const ALLOWED_EXTENSIONS = ['pdf', 'docx'];

    // [등록 버튼 클릭] -> 리스트 숨김, 업로드 표시
    $('#go-upload-btn').on('click', function () {
        $dashboardView.fadeOut(200, function () {
            $uploadView.fadeIn(200);
        });
    });

    // [뒤로가기 버튼 클릭] -> 업로드 숨김, 리스트 표시
    $('#back-to-list-btn').on('click', function () {
        $uploadView.fadeOut(200, function () {
            $dashboardView.fadeIn(200, function () {
                updateSlider();
            });
        });
    });

    // 3. 파일 업로드 기능 (드래그 앤 드롭 & 클릭)

    // 클릭 시 파일 탐색기 열기
    $dropZone.on('click', function () {
        $fileInput.val('');
        $fileInput[0].click();
    });

    // click 재귀 방지
    $fileInput.on('click', function (e) {
        e.stopPropagation();
    });

    // 드래그 효과 (진입)
    $dropZone.on('dragover dragenter', function (e) {
        e.preventDefault();
        e.stopPropagation();
        $(this).addClass('drag-over');
    });

    // 드래그 효과 (이탈/드롭)
    $dropZone.on('dragleave drop', function (e) {
        e.preventDefault();
        e.stopPropagation();
        $(this).removeClass('drag-over');
    });

    // 공통 파일 검증 함수 추가
    function validateFiles(files) {
        if (!files || files.length === 0) {
            alert('업로드할 파일이 없습니다.');
            return null;
        }

        if (files.length > 1) {
            alert('이력서는 한 번에 1개만 업로드할 수 있습니다.');
            return null;
        }

        const file = files[0];
        const fileName = file.name || '';
        const extension = fileName.includes('.')
            ? fileName.split('.').pop().toLowerCase()
            : '';

        if (!ALLOWED_EXTENSIONS.includes(extension)) {
            alert('PDF, DOCX 파일만 업로드할 수 있습니다.');
            return null;
        }

        if (file.size > MAX_FILE_SIZE) {
            alert('파일 크기는 최대 10MB까지 가능합니다.');
            return null;
        }

        return file;
    }

    // 파일 드롭 시 처리
    $dropZone.on('drop', function (e) {
        const files = e.originalEvent.dataTransfer.files;

        // 여러 개 드롭 방지 + 검증
        const file = validateFiles(files);
        if (!file) return;

        handleFileUpload(file);
    });

    // 파일 선택(input) 시 처리
    $fileInput.on('change', function () {
        // 공통 검증 함수 사용
        const file = validateFiles(this.files);
        if (!file) {
            $fileInput.val('');
            return;
        }

        handleFileUpload(file);
    });

    // 실제 업로드 처리
    async function handleFileUpload(file) {
        const formData = new FormData();
        formData.append('model', model);
        formData.append('files', file);

        try {
            const response = await fetch('/resumes', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (!response.ok) {
                alert(result.detail || '업로드 실패');
                return;
            }

            location.href = `/resumes/${result.resume_id}/wait`;
        } catch (error) {
            console.error(error);
            alert('업로드 중 오류가 발생했습니다.');
        } finally {
            $fileInput.val('');
        }
    }

    // 4. 슬라이더 로직

    function getCards() {
        return $resumeList.find('.resume-card');
    }

    function getCardsPerView() {
        if (window.innerWidth <= 768) return 1;
        if (window.innerWidth <= 1024) return 2;
        return 3;
    }

    function getGap() {
        const gapValue = window.getComputedStyle($resumeList[0]).gap;
        return parseInt(gapValue, 10) || 0;
    }

    function updateSlider() {
        if (!$resumeList.length || !$prevBtn.length || !$nextBtn.length) return;

        const $cards = getCards();
        const totalCards = $cards.length;
        const cardsPerView = getCardsPerView();

        if (totalCards === 0) {
            $resumeList.css('transform', 'translateX(0)');
            $prevBtn.hide();
            $nextBtn.hide();
            return;
        }

        if (totalCards <= cardsPerView) {
            currentIndex = 0;
            $resumeList.css('transform', 'translateX(0)');
            $prevBtn.prop('disabled', true).hide();
            $nextBtn.prop('disabled', true).hide();
            return;
        }

        $prevBtn.show();
        $nextBtn.show();

        const $firstCard = $cards.first();
        const cardWidth = $firstCard.outerWidth();
        const gap = getGap();
        const moveUnit = cardWidth + gap;
        const maxIndex = totalCards - cardsPerView;

        if (currentIndex < 0) currentIndex = 0;
        if (currentIndex > maxIndex) currentIndex = maxIndex;

        const moveX = currentIndex * moveUnit;
        $resumeList.css('transform', `translateX(-${moveX}px)`);

        $prevBtn.prop('disabled', currentIndex === 0);
        $nextBtn.prop('disabled', currentIndex === maxIndex);
    }

    $prevBtn.on('click', function () {
        currentIndex -= 1;
        updateSlider();
    });

    $nextBtn.on('click', function () {
        currentIndex += 1;
        updateSlider();
    });

    let resizeTimer = null;
    $(window).on('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            currentIndex = 0;
            updateSlider();
        }, 100);
    });

    $(window).on('load', function () {
        updateSlider();
    });

    updateSlider();
});