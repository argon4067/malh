/**
 * login.js - 로그인 페이지 인터랙션 및 유효성 검사 (jQuery)
 */

function validateInput(input) {
    const $input = $(input);
    const $errorMsg = $input.next('.error-message');
    
    if ($input.val().trim() === "") {
        $input.css("border-color", "var(--error-red)");
        $errorMsg.addClass("show");
    } else {
        $input.css("border-color", "var(--border-color)");
        $errorMsg.removeClass("show");
    }
}

function handleLogin(event) {
    const $userId = $('#userId');
    const $userPw = $('#userPw');

    validateInput($userId[0]);
    validateInput($userPw[0]);

    if ($userId.val().trim() === "" || $userPw.val().trim() === "") {
        event.preventDefault(); 
        return false;
    }

    return true;
}