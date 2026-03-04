document.addEventListener("DOMContentLoaded", function() {
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

    // [Logic 1] 새 비밀번호 유효성 검사
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

    // [Logic 2] 비밀번호 확인 검사
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

    // 실시간 검사 (blur 이벤트 바인딩)
    newPwInput.addEventListener('blur', window.validateNewPw);
    confirmPwInput.addEventListener('blur', window.validateConfirmPw);

    // [Logic 3] 변경하기 버튼 클릭 시 실제 API 통신
    window.submitChange = async function() {
        const isNewValid = window.validateNewPw();
        const isConfirmValid = window.validateConfirmPw();

        if (isNewValid && isConfirmValid) {
            const newPw = newPwInput.value;

            try {
                // 백엔드 API로 새 비밀번호 전송
                const response = await fetch('/auth/change-password', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ new_password: newPw })
                });
                
                const result = await response.json();

                if (response.ok) {
                    // ✅ 프론트엔드에서 확실하게 좀비 쿠키 강제 삭제! (경로별로 모두 폭파)
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/account;"; 
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/auth;"; 

                    // 성공 시 알림 및 재로그인 유도
                    alert(result.message || "비밀번호가 성공적으로 변경되었습니다. 다시 로그인해 주세요.");
                    location.href = "/auth/login";
                } else {
                    // ✅ 실패 시 (기존 비밀번호와 동일한 경우) alert를 띄우고 입력창 비우기
                    alert(result.detail || "비밀번호 변경에 실패했습니다.");
                    newPwInput.value = '';
                    confirmPwInput.value = '';
                    newPwInput.focus();
                }
            } catch (error) {
                console.error("비밀번호 변경 에러:", error);
                alert("서버와 통신 중 오류가 발생했습니다.");
            }
        }
    };
});