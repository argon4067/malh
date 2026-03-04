let isIdChecked = false;
let checkedIdValue = "";

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

async function checkDuplicate() {
    const value = document.getElementById("userId").value;
    const helper = document.getElementById("idHelper");

    if (!value) {
        alert("아이디를 입력해주세요.");
        return;
    }

    // ✅ 서버에 요청하기 전 프론트엔드 단에서 아이디 정규표현식 검사 (영문, 숫자 6~20자)
    const idRegex = /^[A-Za-z0-9]{6,20}$/;
    if (!idRegex.test(value)) {
        alert("아이디 형식에 맞지 않습니다.");
        isIdChecked = false;
        checkedIdValue = "";
        if (helper) {
            helper.innerText = "영문, 숫자 6~20자로 입력해주세요.";
            helper.style.color = "red";
        }
        return; // 형식이 틀리면 여기서 함수 종료
    }

    try {
        // 백엔드 API로 아이디 중복 확인 요청
        const response = await fetch(`/auth/check-id?userId=${encodeURIComponent(value)}`);
        const data = await response.json();

        // DB 확인 결과에 따른 분기 처리
        if (data.exists) {
            // 중복되는 아이디가 있는 경우
            alert("이미 존재하는 아이디입니다.");
            isIdChecked = false;
            checkedIdValue = "";
            if (helper) {
                helper.innerText = "이미 사용 중인 아이디입니다.";
                helper.style.color = "red";
            }
        } else if (data.invalid_format) {
            // 혹시라도 서버단에서 형식이 틀렸다고 판단한 경우
            alert("아이디 형식에 맞지 않습니다.");
            isIdChecked = false;
            checkedIdValue = "";
        } else {
            // 사용 가능한 경우
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

function handleSignup(event) {
    const id = document.getElementById("userId").value;
    const pw = document.getElementById("userPw").value;
    const confirmPw = document.getElementById("userPwConfirm").value;

    const pwRegex = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$/;

    if (!isIdChecked || checkedIdValue !== id) {
        alert("아이디 중복확인을 해주세요.");
        event.preventDefault(); // 폼 제출 확실히 방지
        return false;
    }

    if (!pwRegex.test(pw)) {
        alert("비밀번호 형식을 확인해주세요.");
        event.preventDefault(); 
        return false;
    }

    if (pw !== confirmPw) {
        alert("비밀번호가 일치하지 않습니다.");
        event.preventDefault(); 
        return false;
    }

    return true;
}