/**
 * main.js - 메인 페이지 동작 로직 (jQuery)
 */

$(document).ready(function() {

    // [동작 예시] 스크롤 시 헤더 그림자 강화 효과
    const $header = $('header');
    
    $(window).on('scroll', function() {
        if ($(this).scrollTop() > 50) {
            $header.css({
                'box-shadow': '0 4px 12px rgba(0,0,0,0.1)',
                'transition': 'box-shadow 0.3s ease'
            });
        } else {
            $header.css('box-shadow', '0 2px 8px rgba(0,0,0,0.05)');
        }
    });

    // 버튼 호버 시 동작 정의 (필요 시 로직 추가 가능)
    $('.btn-hero').on('mouseenter', function() {
        // 호버 시 추가 동작 정의 가능
    });
});