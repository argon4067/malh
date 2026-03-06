let isIdChecked = false;
let checkedIdValue = "";

/**
 * 비밀번호 유효성 검사 (실시간)
 */
function validatePassword() {
    const pw = document.getElementById("userPw").value;
    const regex = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$/;
    const helper = document.getElementById("pwHelper");

    if (regex.test(pw)) {
        helper.innerText = "사용 가능한 비밀번호입니다.";
        helper.style.color = "green";
    } else {
        helper.innerText = "8자 이상 영문, 숫자, 특수문자를 포함해야 합니다.";
        helper.style.color = "red";
    }
}

/**
 * 비밀번호 확인 일치 여부 검사 (실시간)
 */
function comparePassword() {
    const pw = document.getElementById("userPw").value;
    const confirmPw = document.getElementById("userPwConfirm").value;
    const helper = document.getElementById("pwConfirmHelper");

    if (pw === confirmPw) {
        helper.innerText = "비밀번호가 일치합니다.";
        helper.style.color = "green";
    } else {
        helper.innerText = "비밀번호가 일치하지 않습니다.";
        helper.style.color = "red";
    }
}

/**
 * 아이디 중복 확인 (탈퇴 계정 체크 포함)
 */
async function checkDuplicate() {
    const value = document.getElementById("userId").value;
    const helper = document.getElementById("idHelper");

    if (!value) {
        alert("아이디를 입력해주세요.");
        return;
    }

    // 아이디 정규표현식 검사 (영문, 숫자 6~20자)
    const idRegex = /^[A-Za-z0-9]{6,20}$/;
    if (!idRegex.test(value)) {
        alert("아이디 형식에 맞지 않습니다.");
        isIdChecked = false;
        checkedIdValue = "";
        if (helper) {
            helper.innerText = "영문, 숫자 6~20자로 입력해주세요.";
            helper.style.color = "red";
        }
        return;
    }

    try {
        // 백엔드 API로 아이디 중복 확인 요청
        const response = await fetch(`/auth/check-id?userId=${encodeURIComponent(value)}`);
        const data = await response.json();

        // 1. 탈퇴한 계정인 경우 (백엔드 응답: is_withdrawn: true)
        if (data.is_withdrawn) {
            alert("탈퇴처리된 계정입니다.");
            isIdChecked = false;
            checkedIdValue = "";
            if (helper) {
                helper.innerText = "탈퇴처리된 계정입니다.";
                helper.style.color = "red";
            }
        } 
        // 2. 이미 사용 중인 일반 계정인 경우
        else if (data.exists) {
            alert("이미 존재하는 아이디입니다.");
            isIdChecked = false;
            checkedIdValue = "";
            if (helper) {
                helper.innerText = "이미 사용 중인 아이디입니다.";
                helper.style.color = "red";
            }
        } 
        // 3. 서버단 형식 검증 실패 시
        else if (data.invalid_format) {
            alert("아이디 형식에 맞지 않습니다.");
            isIdChecked = false;
            checkedIdValue = "";
        } 
        // 4. 사용 가능한 경우
        else {
            alert(value + "은(는) 사용 가능한 아이디입니다.");
            isIdChecked = true;
            checkedIdValue = value;
            if (helper) {
                helper.innerText = "중복 확인 완료";
                helper.style.color = "green";
            }
        }

    } catch (error) {
        console.error("중복 확인 에러:", error);
        alert("서버와 통신 중 오류가 발생했습니다.");
    }
}

/**
 * 회원가입 폼 제출 처리
 */
function handleSignup(event) {
    const id = document.getElementById("userId").value;
    const pw = document.getElementById("userPw").value;
    const confirmPw = document.getElementById("userPwConfirm").value;

    const pwRegex = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$/;

    // 중복 확인 여부 및 입력값 변경 여부 확인
    if (!isIdChecked || checkedIdValue !== id) {
        alert("아이디 중복확인을 해주세요.");
        event.preventDefault(); 
        return false;
    }

    // 비밀번호 형식 재검증
    if (!pwRegex.test(pw)) {
        alert("비밀번호 형식을 확인해주세요.");
        event.preventDefault(); 
        return false;
    }

    // 비밀번호 일치 재검증
    if (pw !== confirmPw) {
        alert("비밀번호가 일치하지 않습니다.");
        event.preventDefault(); 
        return false;
    }

    // 모든 검증 통과 시
    alert("회원가입이 완료되었습니다! 로그인을 해주세요"); 
    // 실제 서버로 폼 데이터 전송
    event.target.submit(); 

    return true;
}