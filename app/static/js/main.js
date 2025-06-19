// 全域 JavaScript 功能
$(document).ready(function() {
    // 自動關閉 alert 訊息
    setTimeout(function() {
        const alertsBeforeClose = $('.alert');
        
        // 記錄將被關閉的 Alert
        alertsBeforeClose.each(function(index) {
            const classes = $(this).attr('class');
            
            // 檢查是否為永久性格式說明
            if ($(this).hasClass('format-info-permanent')) {
                // 永久性格式說明不關閉
                return;
            }
        });
        
        // 修改為只關閉非永久性的 Alert
        $('.alert:not(.format-info-permanent)').fadeOut();
    }, 5000);
    
    // 初始化 tooltips
    $('[data-toggle="tooltip"]').tooltip();
}); 