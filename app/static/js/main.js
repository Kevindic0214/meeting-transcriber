// 全域 JavaScript 功能
$(document).ready(function() {
    console.log('🔍 main.js 已載入並執行');
    
    // 檢查 jQuery 和 Bootstrap 是否正確載入
    console.log('📚 函式庫檢查:', {
        'jQuery': typeof $ !== 'undefined' ? $.fn.jquery : '未載入',
        'Bootstrap': typeof $.fn.modal !== 'undefined' ? '已載入' : '未載入',
        'Gentelella': typeof $.fn.fullCalendar !== 'undefined' ? '已載入' : '未確定'
    });
    
    // 檢查頁面上的 Alert 元素
    const alerts = $('.alert');
    console.log(`🚨 找到 ${alerts.length} 個 Alert 元素:`, alerts);
    alerts.each(function(index) {
        console.log(`  Alert ${index + 1}: 類別=${$(this).attr('class')}, 內容=${$(this).text().trim()}`);
    });
    
    // 自動關閉 alert 訊息 - 增加調試訊息
    console.log('⏱️ 設定 Alert 自動關閉計時器 (5秒)');
    setTimeout(function() {
        console.log('⏰ Alert 自動關閉觸發');
        const alertsBeforeClose = $('.alert');
        console.log(`  關閉前有 ${alertsBeforeClose.length} 個 Alert 元素`);
        
        // 記錄將被關閉的 Alert
        alertsBeforeClose.each(function(index) {
            const classes = $(this).attr('class');
            console.log(`  準備關閉 Alert ${index + 1}: ${classes}`);
            
            // 檢查是否為永久性格式說明
            if ($(this).hasClass('format-info-permanent')) {
                console.warn('⚠️ 嘗試關閉永久性格式說明! 類別:', classes);
            }
        });
        
        // 修改為只關閉非永久性的 Alert
        $('.alert:not(.format-info-permanent)').fadeOut(function() {
            console.log('🔄 Alert 淡出完成:', $(this).attr('class'));
        });
        
        // 檢查關閉後的狀態
        setTimeout(function() {
            const alertsAfterClose = $('.alert:visible');
            console.log(`  關閉後仍可見的 Alert: ${alertsAfterClose.length} 個`);
            alertsAfterClose.each(function(index) {
                console.log(`    仍可見 ${index + 1}: ${$(this).attr('class')}`);
            });
        }, 1000);
    }, 5000);
    
    // 初始化 tooltips
    $('[data-toggle="tooltip"]').tooltip();
    
    console.log('✅ main.js 初始化完成');
}); 