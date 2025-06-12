// 全域 JavaScript 功能
$(document).ready(function() {
    // 自動關閉 alert 訊息
    setTimeout(function() {
        $('.alert').fadeOut();
    }, 5000);
    
    // 初始化 tooltips
    $('[data-toggle="tooltip"]').tooltip();
}); 