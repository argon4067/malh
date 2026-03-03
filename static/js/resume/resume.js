/**
 * resume.js - 이력서 관리 화면 전환 및 업로드 로직 (jQuery)
 */

$(function () {
    // 1. 화면 요소 참조
    const $dashboardView = $('#dashboard-view');
    const $uploadView = $('#upload-view');
    const $dropZone = $('#dropZone');
    const $fileInput = $('#fileInput');

    // ✅ 변경: 서버로 보낼 값
    const userId = $('#userIdInput').val() || '1';
    const model = $('#modelInput').val() || 'gpt-4o-mini';

    // 2. 화면 전환 이벤트

    // [등록 버튼 클릭] -> 리스트 숨김, 업로드 표시
    $('#go-upload-btn').on('click', function () {
        $dashboardView.fadeOut(200, function () {
            $uploadView.fadeIn(200);
        });
    });

    // [뒤로가기 버튼 클릭] -> 업로드 숨김, 리스트 표시
    $('#back-to-list-btn').on('click', function () {
        $uploadView.fadeOut(200, function () {
            $dashboardView.fadeIn(200);
        });
    });

    // 3. 파일 업로드 기능 (드래그 앤 드롭 & 클릭)

    // ✅ 유지: 클릭 시 파일 탐색기 열기
    $dropZone.on('click', function (e) {
        if (e.target !== this) return;
        $fileInput.trigger('click');
    });

    // ✅ 유지: click 재귀 방지
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

    // 파일 드롭 시 처리
    $dropZone.on('drop', function (e) {
        const files = e.originalEvent.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    // 파일 선택(input) 시 처리
    $fileInput.on('change', function () {
        if (this.files.length > 0) {
            handleFileUpload(this.files[0]);
        }
    });

    // ✅ 변경: 실제 업로드 처리
    function handleFileUpload(file) {
        const formData = new FormData();
        formData.append('user_id', userId);
        formData.append('model', model);
        formData.append('file', file);

        fetch('/resumes', {
            method: 'POST',
            body: formData
        })
        .then(async (response) => {
            const result = await response.json();

            if (!response.ok) {
                alert(result.detail || '업로드 실패');
                return;
            }

            // ✅ 변경: 업로드 성공 -> wait 페이지 이동
            location.href = `/resumes/${result.resume_id}/wait?model=${encodeURIComponent(result.model)}`;
        })
        .catch((error) => {
            console.error(error);
            alert('업로드 중 오류가 발생했습니다.');
        });
    }

    // ✅ 삭제 대상:
    // - createResumeCard()
    // - updateTotalCount()
    // - 프론트에서 가짜 카드 prepend 하는 로직
    // - delete-btn 동적 삭제 시뮬레이션
});