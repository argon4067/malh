document.addEventListener("DOMContentLoaded", function() {
    // ✅ 1. 요소 가져오기
    const currentPwInput = document.getElementById('currentPw');
    const currentPwError = document.getElementById('currentPwError');
    
    const newPwInput = document.getElementById('newPw');
    const confirmPwInput = document.getElementById('confirmPw');
    const newPwError = document.getElementById('newPwError');
    const confirmError = document.getElementById('confirmError');

    // [Helper] 에러 메시지 표시
    function showError(input, errorElement, message) {
        input.classList.add('input-error');
        errorElement.innerText = message;
        errorElement.style.display = 'block';
    }

    // [Helper] 에러 메시지 숨김
    function hideError(input, errorElement) {
        input.classList.remove('input-error');
        errorElement.style.display = 'none';
    }

    // ✅ 유효성 검사 함수들을 전역(window)에 등록
    window.validateCurrentPw = function() {
        const val = currentPwInput.value;
        if (!val) {
            showError(currentPwInput, currentPwError, "현재 비밀번호를 입력해 주세요.");
            return false;
        }
        hideError(currentPwInput, currentPwError);
        return true;
    };

    window.validateNewPw = function() {
        const val = newPwInput.value;
        const regex = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$/;

        if (!val) {
            showError(newPwInput, newPwError, "새 비밀번호를 입력해 주세요.");
            return false;
        }
        if (!regex.test(val)) {
            showError(newPwInput, newPwError, "8자 이상 영문, 숫자, 특수문자를 조합해 주세요.");
            return false;
        }

        hideError(newPwInput, newPwError);
        return true;
    };

    window.validateConfirmPw = function() {
        const val = confirmPwInput.value;
        const original = newPwInput.value;

        if (!val) {
            showError(confirmPwInput, confirmError, "비밀번호 확인을 입력해 주세요.");
            return false;
        }
        if (val !== original) {
            showError(confirmPwInput, confirmError, "비밀번호가 일치하지 않습니다.");
            return false;
        }

        hideError(confirmPwInput, confirmError);
        return true;
    };

    // 실시간 검사 (blur 이벤트)
    currentPwInput.addEventListener('blur', window.validateCurrentPw);
    newPwInput.addEventListener('blur', window.validateNewPw);
    confirmPwInput.addEventListener('blur', window.validateConfirmPw);

    // ✅ 변경하기 버튼 클릭 시 실제 API 통신
    window.submitChange = async function(event) {
        // 브라우저 기본 폼 제출 동작을 막아 405/400 중복 에러 방지
        if (event) event.preventDefault();

        const isCurrentValid = window.validateCurrentPw();
        const isNewValid = window.validateNewPw();
        const isConfirmValid = window.validateConfirmPw();

        if (isCurrentValid && isNewValid && isConfirmValid) {
            try {
                const response = await fetch('/auth/change-password', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ 
                        current_password: currentPwInput.value, 
                        new_password: newPwInput.value 
                    })
                });
                
                const result = await response.json();

                // ✅ 콘솔 에러를 피하기 위해 response.ok 대신 서버가 보낸 success 필드 확인
                // (백엔드에서 실패 시에도 200 OK를 보내야 함)
                if (result.success) {
                    // 쿠키 강제 삭제
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/account;"; 
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/auth;"; 

                    alert(result.message || "비밀번호가 성공적으로 변경되었습니다. 다시 로그인해 주세요.");
                    location.href = "/auth/login";
                } else {
                    // 서버 응답은 200이지만 로직상 실패한 경우 (비밀번호 틀림 등)
                    alert(result.detail || "비밀번호 변경에 실패했습니다.");
                    currentPwInput.value = '';
                    newPwInput.value = '';
                    confirmPwInput.value = '';
                    currentPwInput.focus();
                }
            } catch (error) {
                // 네트워크가 완전히 끊긴 경우에만 발생
                console.error("비밀번호 변경 에러:", error);
            }
        }
        return false;
    };
});