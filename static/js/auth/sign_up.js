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

function checkDuplicate() {
    const value = document.getElementById("userId").value;

    if (!value) {
        alert("아이디를 입력해주세요.");
        return;
    }

    alert(value + "은(는) 사용 가능한 아이디입니다.");
    isIdChecked = true;
    checkedIdValue = value;
    
    // 중복확인 완료 시 텍스트 피드백 변경 추가
    const helper = document.getElementById("idHelper");
    helper.innerText = "중복 확인 완료";
    helper.style.color = "green";
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