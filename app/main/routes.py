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

from app.db import add_meeting, get_all_meetings, get_meeting_by_id
from app.services.processing import process_meeting
from . import bp

logger = logging.getLogger(__name__)

@bp.route('/')
def index():
    """首頁 - 顯示上傳介面"""
    return render_template('index.html')

@bp.route('/api/recent-meetings')
def get_recent_meetings():
    """API: 獲取最近的會議記錄（用於首頁顯示）"""
    try:
        # 獲取最近5筆會議記錄
        all_meetings = get_all_meetings()
        recent_meetings = all_meetings[:5] if all_meetings else []
        
        # 格式化回傳資料
        formatted_meetings = []
        for meeting in recent_meetings:
            formatted_meeting = {
                'id': meeting['id'],
                'original_filename': meeting['original_filename'],
                'status': meeting['status'],
                'created_at': meeting['created_at'],
                'duration': meeting['duration'],
                'num_speakers': meeting['num_speakers']
            }
            formatted_meetings.append(formatted_meeting)
        
        return jsonify({
            'status': 'success',
            'meetings': formatted_meetings,
            'total_count': len(all_meetings) if all_meetings else 0
        })
    except Exception as e:
        logger.error(f"獲取最近會議記錄時發生錯誤: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '獲取會議記錄失敗'
        }), 500

@bp.route('/upload', methods=['POST'])
def upload_file():
    """處理檔案上傳"""
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
        # request.content_length 包含了整個請求的大小，這裡我們直接用 file seek 來取得檔案大小
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        file.seek(0, 0) # 將指標移回開頭
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

@bp.route('/meetings/<meeting_id>/stream')
def meeting_progress_stream(meeting_id):
    """提供會議處理進度的 SSE 串流"""
    def generate_progress():
        progress_tracker = current_app.progress_tracker
        q = progress_tracker.get(meeting_id)
        
        if not q:
            # 如果處理已開始但佇列不存在，表示可能已完成或出錯
            # 發送一個完成事件來確保前端停止輪詢
            error_message = json.dumps({'step': 'error', 'message': '無法追蹤進度，可能處理已完成或發生錯誤。'})
            yield f"data: {error_message}\n\n"
            return

        while True:
            try:
                message = q.get(timeout=30)  # 等待新訊息，設置超時以防萬一
                if message.get('status') == 'done':
                    break
                
                # 格式化為 SSE 格式
                sse_data = f"data: {json.dumps(message)}\n\n"
                yield sse_data
            except Exception:
                # 如果超時或佇列為空，跳出循環
                break
    
    # 回傳一個串流回應，確保代理不會緩衝
    response = Response(generate_progress(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

@bp.route('/meetings/<meeting_id>')
def meeting_detail(meeting_id):
    """會議詳情頁面"""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        flash('找不到指定的會議記錄', 'error')
        return redirect(url_for('main.meetings_list'))
    
    return render_template('meeting_detail.html', meeting=meeting)

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
