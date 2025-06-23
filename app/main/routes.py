import uuid
from pathlib import Path
from threading import Thread
from werkzeug.utils import secure_filename
import logging
import os
import json
from flask import (
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
    current_app,
    jsonify,
    Response
)
import time
from datetime import datetime

from app.db import add_meeting, get_all_meetings, get_meeting_by_id, get_meeting_summary
from app.services.processing import process_meeting
from utils.export_utils import format_summary_for_export, create_summary_docx
from . import bp

logger = logging.getLogger(__name__)

# ===============================================
# 網頁路由
# ===============================================

@bp.route('/')
def index():
    """首頁 - 顯示上傳介面"""
    return render_template('index.html')

@bp.route('/upload', methods=['POST'])
def upload_file():
    """處理檔案上傳（前端表單提交）"""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': '沒有選擇檔案'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '沒有選擇檔案'}), 400
    
    allowed_extensions = {'.m4a', '.mp3', '.wav', '.flac', '.webm'}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        return jsonify({'status': 'error', 'message': '不支援的檔案格式'}), 400
    
    config = current_app.config
    meeting_id = str(uuid.uuid4())
    filename = secure_filename(f"{meeting_id}_{file.filename}")
    file_path = config['UPLOADS_FOLDER'] / filename
    
    try:
        # 檢查檔案大小
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        file.seek(0, 0)
        if file_length > config['MAX_CONTENT_LENGTH']:
            return jsonify({'status': 'error', 'message': f'檔案大小超過 {config["MAX_CONTENT_LENGTH"] // 1024 // 1024}MB 的限制'}), 413
            
        file.save(file_path)
    except Exception as e:
        logger.error(f"儲存檔案失敗: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '儲存檔案時發生錯誤'}), 500

    num_speakers = request.form.get('num_speakers')
    if num_speakers and num_speakers.isdigit():
        num_speakers = int(num_speakers)
    else:
        num_speakers = None
    
    add_meeting(meeting_id, filename, file.filename)
    
    app = current_app._get_current_object()
    
    thread = Thread(target=process_meeting, args=(app, meeting_id, str(file_path), num_speakers))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'success', 'meeting_id': meeting_id})

@bp.route('/meetings')
def meetings_list():
    """會議列表頁面"""
    meetings = get_all_meetings()
    return render_template('meetings.html', meetings=meetings)

@bp.route('/meetings/<meeting_id>')
def meeting_detail(meeting_id):
    """會議詳情頁面"""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        flash('找不到指定的會議記錄', 'error')
        return redirect(url_for('main.meetings_list'))
    
    return render_template('meeting_detail.html', meeting=meeting)

# ===============================================
# 檔案操作路由
# ===============================================

@bp.route('/stream_audio/<meeting_id>')
def stream_audio(meeting_id):
    """串流處理後的音訊檔案"""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        return "Meeting not found", 404
        
    # 我們假設處理後的音訊是 wav 格式
    processed_filename = f"{meeting_id}.wav"
    file_path = current_app.config['PROCESSED_FOLDER'] / processed_filename
    
    if not file_path.exists():
        return "Processed audio file not found", 404
        
    return send_file(file_path, mimetype='audio/wav')

@bp.route('/download/<meeting_id>/summary/<file_type>')
def download_summary(meeting_id, file_type):
    """下載會議摘要檔案 (txt 或 docx)"""
    # 檢查支援的檔案類型
    if file_type not in ['txt', 'docx']:
        flash('不支援的檔案類型', 'error')
        return redirect(url_for('main.meeting_detail', meeting_id=meeting_id))
        
    # 獲取會議資訊和摘要
    meeting = get_meeting_by_id(meeting_id)
    summary_data = get_meeting_summary(meeting_id)

    if not meeting or not summary_data:
        flash('找不到會議摘要', 'error')
        return redirect(url_for('main.meeting_detail', meeting_id=meeting_id))
        
    original_name = Path(meeting['original_filename']).stem
    
    if file_type == 'txt':
        # 生成 TXT 內容
        content = format_summary_for_export(summary_data, meeting)
        
        # 準備下載
        return Response(
            content,
            mimetype='text/plain; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="{original_name}_summary.txt"'
            }
        )
    
    elif file_type == 'docx':
        # 生成 Word 文件
        docx_file = create_summary_docx(summary_data, meeting)
        
        # 準備下載
        return send_file(
            docx_file,
            as_attachment=True,
            download_name=f"{original_name}_summary.docx",
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

@bp.route('/download/<meeting_id>/<file_type>')
def download_file_route(meeting_id, file_type):
    """下載處理結果檔案"""
    field_map = {
        'srt': 'srt_path',
        'rttm': 'rttm_path', 
        'speaker_srt': 'speaker_srt_path'
    }
    
    if file_type not in field_map:
        flash('不支援的檔案類型', 'error')
        return redirect(url_for('main.meeting_detail', meeting_id=meeting_id))
    
    meeting = get_meeting_by_id(meeting_id)
    if not meeting or not meeting[field_map[file_type]]:
        flash('檔案不存在或尚未生成', 'error')
        return redirect(url_for('main.meeting_detail', meeting_id=meeting_id))
    
    file_path = current_app.config['BASE_DIR'] / meeting[field_map[file_type]]
    if not file_path.exists():
        flash('檔案遺失', 'error')
        return redirect(url_for('main.meeting_detail', meeting_id=meeting_id))
        
    original_name = Path(meeting['original_filename']).stem
    extension_map = {
        'srt': '.srt',
        'rttm': '.rttm',
        'speaker_srt': '_語者標註.srt'
    }
    download_name = f"{original_name}{extension_map[file_type]}"
    
    return send_file(file_path, as_attachment=True, download_name=download_name)

# ===============================================
# SSE 串流路由
# ===============================================

@bp.route('/meetings/<meeting_id>/stream')
def meeting_progress_stream(meeting_id):
    """提供會議處理進度的 SSE 串流"""
    logger.info(f"SSE: Client connected for meeting_id: {meeting_id}")
    # 在路由函數中獲取 progress_tracker，而不是在生成器中
    progress_tracker = current_app.progress_tracker
    q = progress_tracker.get(meeting_id)
    
    def generate_progress():
        logger.info(f"SSE - {meeting_id}: Starting progress generator.")
        if not q:
            logger.warning(f"SSE - {meeting_id}: No progress queue found. Sending error message.")
            # 如果處理已開始但佇列不存在，表示可能已完成或出錯
            # 發送一個完成事件來確保前端停止輪詢
            error_message = json.dumps({'step': 'error', 'message': '無法追蹤進度，處理程序可能未正確啟動或已結束。'})
            yield f"data: {error_message}\n\n"
            return

        client_connected = True
        try:
            while client_connected:
                try:
                    message = q.get(timeout=30)  # 等待新訊息，設置超時以防萬一
                    logger.info(f"SSE - {meeting_id}: Got message from queue: {message}")

                    if message.get('status') == 'done':
                        logger.info(f"SSE - {meeting_id}: 'done' message received. Breaking loop.")
                        break
                    
                    # 格式化為 SSE 格式
                    sse_data = f"data: {json.dumps(message)}\n\n"
                    logger.info(f"SSE - {meeting_id}: Sending data to client: {sse_data.strip()}")
                    yield sse_data
                except Exception as e:
                    # 如果超時或佇列為空，跳出循環
                    logger.info(f"SSE - {meeting_id}: Queue timeout or empty. Breaking loop. Exception: {e}")
                    break
        except GeneratorExit:
            # This exception is raised when the client disconnects
            client_connected = False
            logger.info(f"SSE - {meeting_id}: Client disconnected. Closing generator.")
        finally:
            logger.info(f"SSE - {meeting_id}: Progress generator finished.")
    
    # 回傳一個串流回應，確保代理不會緩衝
    response = Response(generate_progress(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response
