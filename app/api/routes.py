import logging
from pathlib import Path

from flask import jsonify, current_app, Response

from . import bp
from app.db import get_meeting_by_id, delete_meeting_by_id
from utils.subtitle_processing import parse_srt_content

logger = logging.getLogger(__name__)

@bp.route('/meeting/<meeting_id>/status')
def get_meeting_status(meeting_id):
    """API: 獲取會議處理狀態"""
    meeting = get_meeting_by_id(meeting_id)
    if meeting:
        return jsonify({'status': meeting['status'], 'error_message': meeting['error_message']})
    else:
        return jsonify({'status': 'not_found'}), 404

def _get_subtitle_content(meeting_id):
    """輔助函式：獲取字幕內容，返回 (內容, 原始檔名) 或 (錯誤JSON, 狀態碼)。"""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        logger.warning(f"API請求：找不到會議記錄: {meeting_id}")
        return jsonify({'error': '會議記錄不存在', 'code': 'MEETING_NOT_FOUND'}), 404
    
    if meeting['status'] != 'completed':
        logger.info(f"API請求：會議 {meeting_id} 尚未完成，狀態: {meeting['status']}")
        return jsonify({
            'error': '會議尚未處理完成', 
            'code': 'PROCESSING_NOT_COMPLETE', 
            'current_status': meeting['status']
        }), 400

    speaker_srt_path = meeting['speaker_srt_path']
    if not speaker_srt_path:
        logger.error(f"會議 {meeting_id} 的字幕路徑為空")
        return jsonify({'error': '字幕檔案路徑不存在', 'code': 'SUBTITLE_PATH_MISSING'}), 404

    subtitle_file = current_app.config['BASE_DIR'] / speaker_srt_path
    if not subtitle_file.exists():
        logger.error(f"字幕檔案於檔案系統中不存在: {subtitle_file}")
        return jsonify({'error': '字幕檔案遺失', 'code': 'SUBTITLE_FILE_MISSING'}), 404
        
    try:
        content = subtitle_file.read_text(encoding='utf-8')
        logger.info(f"成功為會議 {meeting_id} 載入字幕")
        return content, meeting['original_filename']
    except Exception as e:
        logger.error(f"讀取字幕檔案時發生錯誤: {e}", exc_info=True)
        return jsonify({'error': '讀取字幕檔案失敗', 'code': 'FILE_READ_ERROR'}), 500

@bp.route('/meeting/<meeting_id>/subtitle')
def get_meeting_subtitle(meeting_id):
    """API: 獲取原始純文字字幕"""
    result = _get_subtitle_content(meeting_id)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], str):
        content, original_filename = result
        return Response(content, mimetype='text/plain; charset=utf-8', headers={
            'X-Meeting-ID': meeting_id,
            'X-Original-Filename': original_filename
        })
    return result # 這是錯誤回應 (jsonify, status)

@bp.route('/meeting/<meeting_id>/subtitle/formatted')
def get_meeting_subtitle_formatted(meeting_id):
    """API: 獲取格式化為 JSON 的字幕"""
    result = _get_subtitle_content(meeting_id)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], str):
        content, _ = result
        segments = parse_srt_content(content)
        return jsonify({
            'meeting_id': meeting_id,
            'total_segments': len(segments),
            'segments': segments
        })
    return result # 這是錯誤回應

@bp.route('/meeting/<meeting_id>/delete', methods=['DELETE'])
def delete_meeting(meeting_id):
    """API: 刪除指定的會議記錄及其相關檔案"""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        return jsonify({'status': 'error', 'message': '會議記錄不存在'}), 404

    try:
        config = current_app.config
        
        # 刪除上傳的原始檔案
        if meeting['filename']:
            uploaded_file = config['UPLOADS_FOLDER'] / meeting['filename']
            if uploaded_file.exists():
                uploaded_file.unlink()
                logger.info(f"已刪除上傳檔案: {uploaded_file}")

        # 刪除處理過程中的檔案
        for ext in ['webm', 'wav']:
            processed_file = config['PROCESSED_FOLDER'] / f"{meeting_id}.{ext}"
            if processed_file.exists():
                processed_file.unlink()
                logger.info(f"已刪除處理檔案: {processed_file}")

        # 刪除輸出結果檔案
        for path_key in ['srt_path', 'rttm_path', 'speaker_srt_path']:
            if meeting[path_key]:
                output_file = config['BASE_DIR'] / meeting[path_key]
                if output_file.exists():
                    output_file.unlink()
                    logger.info(f"已刪除輸出檔案: {output_file}")
        
        delete_meeting_by_id(meeting_id)
        
        logger.info(f"已成功刪除會議記錄: {meeting_id}")
        return jsonify({'status': 'success', 'message': '會議記錄已成功刪除'})
    except Exception as e:
        logger.error(f"刪除會議時發生未知錯誤 (ID: {meeting_id}): {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '伺服器內部錯誤'}), 500
