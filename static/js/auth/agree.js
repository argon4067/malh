/**
 * agree.js - 약관 동의 페이지 동작 로직 (jQuery)
 * '말해뭐해' 모의면접 서비스 맞춤형 약관 적용 및 모달 중앙 정렬
 */

$(document).ready(function() {
    const $checkAllBox = $('#checkAll');
    const $allCheckboxes = $('.terms-list input[type="checkbox"]');
    const $requiredTerms = $('.terms-list input.required');
    const $nextBtn = $('#nextBtn');
    const $modal = $('#termsModal');
    const $modalTitle = $('#modalTitle');
    const $modalBody = $('#modalBody');

    // ✅ 실제 약관 데이터 ('말해뭐해' 모의면접 서비스 맞춤형)
    const termsData = {
        service: `[서비스 이용약관]

제1조 (목적)
본 약관은 회사가 제공하는 ‘말해뭐해’ 모의면접 및 면접 피드백 서비스(이하 “서비스”)의 이용 조건 및 절차, 회사와 회원 간의 권리·의무 및 책임 사항을 규정합니다. 

제2조 (용어 정의) 
1. “회원”이라 함은 본 약관에 동의하고 서비스를 이용하는 자를 의미합니다. 
2. “서비스”란 회사가 제공하는 모의면접 연습, AI 피드백 제공 웹사이트 및 관련 기능을 의미합니다. 
3. “콘텐츠”란 서비스 내에서 제공되는 면접 질문, 분석 결과, 통계 자료 등을 의미합니다. 

제3조 (약관의 효력 및 변경) 
1. 본 약관은 서비스 화면에 게시함으로써 효력이 발생합니다. 
2. 회사는 관련 법령을 위반하지 않는 범위 내에서 약관을 개정할 수 있습니다. 

제4조 (서비스 이용 및 의무) 
1. 회사는 회원에게 맞춤형 모의면접 환경 및 분석 정보를 제공합니다. 
2. 회원은 면접 연습 및 역량 향상 목적으로만 서비스를 이용해야 합니다.
3. 회원은 시스템의 정상적인 운영을 방해하거나, 부정한 방법으로 데이터를 수집·가공하는 행위를 해서는 안 됩니다. 

제5조 (콘텐츠의 저작권) 
서비스 내 제공되는 면접 질문 및 분석 모델의 저작권은 회사에 있으며 무단 복제·배포를 금지합니다. 단, 회원이 직접 녹음한 면접 답변 데이터의 권리는 회원 본인에게 있습니다.

제6조 (면책 조항) 
회사는 AI 피드백 및 분석 결과의 완벽한 정확성이나 실제 취업(합격)을 보장하지 않으며, 이를 참고하여 내린 회원의 결정에 대해 책임지지 않습니다.`,

        privacy: `[개인정보 수집·이용 동의서]

당사는 회원 가입 및 모의면접 서비스 제공을 위하여 아래와 같이 개인정보를 수집·이용합니다. 

1. 수집 항목 
- 필수 정보: 아이디, 비밀번호
- 서비스 이용 시 수집되는 정보: 모의면접 음성 데이터, 면접 답변 텍스트, 접속 기록 등

2. 수집·이용 목적 
- 회원 가입 및 본인 확인, 계정 관리
- 모의면접 서비스 제공 및 AI 기반 면접 피드백(목소리, 답변 내용 등) 분석
- 서비스 품질 개선 및 신규 AI 모델 학습(비식별화 처리 후 사용)
- 고객 문의 및 민원 처리 

3. 보유·이용 기간 
- 회원 탈퇴 시 즉시 파기. 
- 단, 회원이 직접 삭제하지 않은 모의면접 음성 데이터는 서비스 품질 관리를 위해 최대 1년간 보관 후 파기될 수 있습니다. (관련 법령에 따라 보존할 필요가 있는 경우 해당 법령에 따름)

4. 동의를 거부할 권리 및 불이익 
이용자는 개인정보 수집·이용 동의를 거부할 권리가 있습니다. 다만, 필수 항목 및 면접 분석을 위한 데이터 제공에 동의하지 않으실 경우 모의면접 서비스 이용이 제한될 수 있습니다.`,
    };

    // [전체 동의] 체크박스 이벤트
    $checkAllBox.on('change', function() {
        $allCheckboxes.prop('checked', $(this).prop('checked'));
        updateButtonState();
    });

    // [개별 체크박스] 이벤트
    $allCheckboxes.on('change', function() {
        const allChecked = $allCheckboxes.length === $allCheckboxes.filter(':checked').length;
        $checkAllBox.prop('checked', allChecked);
        updateButtonState();
    });

    // 필수 약관 동의 여부에 따른 버튼 활성화
    function updateButtonState() {
        const requiredAllChecked = $requiredTerms.length === $requiredTerms.filter(':checked').length;
        if (requiredAllChecked) {
            $nextBtn.prop('disabled', false).addClass('active');
        } else {
            $nextBtn.prop('disabled', true).removeClass('active');
        }
    }

    // 모달 열기 (HTML의 onclick에서 호출할 수 있도록 window 객체에 할당)
    window.openModal = function(type) {
        // 🔥 화면 정중앙 배치를 위해 CSS에서 설정한 align-items, justify-content가 먹히도록 flex로 엽니다.
        $modal.css('display', 'flex'); 
        
        if (type === 'service') {
            $modalTitle.text("서비스 이용약관");
            $modalBody.text(termsData.service);
        } else if (type === 'privacy') {
            $modalTitle.text("개인정보 수집 및 이용 동의");
            $modalBody.text(termsData.privacy);
        } else if (type === 'marketing') {
            $modalTitle.text("마케팅 정보 수신 동의");
            $modalBody.text(termsData.marketing);
        }
    };

    // 모달 닫기
    window.closeModal = function() {
        $modal.hide();
    };

    // 모달 외부 클릭 시 닫기
    $(window).on('click', function(event) {
        if ($(event.target).is($modal)) {
            closeModal();
        }
    });

    // 다음 단계로 이동
    window.goToNextStep = function() {
        if (!$nextBtn.prop('disabled')) {
            location.href = '/auth/signup';
        } else {
            alert("필수 약관에 동의해 주세요.");
        }
    };
});