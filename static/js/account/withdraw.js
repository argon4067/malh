document.addEventListener("DOMContentLoaded", function() {
    const agreeCheck = document.getElementById('agreeCheck');
    const withdrawBtn = document.getElementById('withdrawBtn');

    // 초기 버튼 상태 설정 (비활성화)
    withdrawBtn.disabled = true;

    // [Logic 1] 체크박스 상태에 따라 버튼 활성화/비활성화
    agreeCheck.addEventListener('change', function() {
        if (agreeCheck.checked) {
            withdrawBtn.classList.add('active');
            withdrawBtn.disabled = false;
        } else {
            withdrawBtn.classList.remove('active');
            withdrawBtn.disabled = true;
        }
    });

    // [Logic 2] 탈퇴 처리 실행 (백엔드 통신)
    withdrawBtn.addEventListener('click', async function() {
        if (!agreeCheck.checked) {
            alert("탈퇴 유의사항에 동의해 주세요.");
            return;
        }

        // 최종 확인 컨펌창
        if (confirm("정말로 탈퇴하시겠습니까? 이 동작은 취소할 수 없습니다.")) {
            try {
                // 백엔드 API로 탈퇴 요청
                const response = await fetch('/auth/withdraw', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const result = await response.json();

                if (response.ok) {
                    // ✅ 프론트엔드에서 확실하게 좀비 쿠키 강제 삭제
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/account;"; 
                    document.cookie = "login_user=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/auth;"; 

                    alert(result.message || "회원 탈퇴 되었습니다.");
                    // 메인 페이지로 이동
                    location.href = "/";
                } else {
                    alert(result.detail || "회원 탈퇴 처리에 실패했습니다.");
                }
            } catch (error) {
                console.error("탈퇴 에러:", error);
                alert("서버와 통신 중 오류가 발생했습니다.");
            }
        }
    });
});