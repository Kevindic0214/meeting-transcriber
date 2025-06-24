import logging
from pathlib import Path
from threading import Thread

from flask import jsonify, current_app, Response, request
from werkzeug.utils import secure_filename
import uuid
import os

from . import bp
from app.db import (get_meeting_by_id, delete_meeting_by_id, get_meeting_summary, 
                    save_meeting_summary, get_speaker_names, get_all_meetings, 
                    add_meeting, update_speaker_name, delete_speaker_name,
                    update_supplementary_summary)
from utils.subtitle_processing import parse_srt_content
from utils.document_parser import read_document_text
from utils.transcription_processor import create_summary_prompt, parse_summary_from_json

logger = logging.getLogger(__name__)

# ===============================================
# 會議基本管理 API
# ===============================================

@bp.route('/recent-meetings')
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

@bp.route('/meeting', methods=['POST'])
def create_meeting():
    """API: 創建新會議並上傳檔案"""
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
    
    # 啟動後台處理
    from app.services.processing import process_meeting
    app = current_app._get_current_object()
    thread = Thread(target=process_meeting, args=(app, meeting_id, str(file_path), num_speakers))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'success', 'meeting_id': meeting_id})

@bp.route('/meeting/<meeting_id>/status')
def get_meeting_status(meeting_id):
    """API: 獲取會議處理狀態"""
    meeting = get_meeting_by_id(meeting_id)
    if meeting:
        return jsonify({'status': meeting['status'], 'error_message': meeting['error_message']})
    else:
        return jsonify({'status': 'not_found'}), 404

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

# ===============================================
# 輔助文件處理 API
# ===============================================

@bp.route('/meeting/<meeting_id>/process-supplement', methods=['POST'])
def process_supplementary_file(meeting_id):
    """API: 處理輔助文件，產生摘要並儲存"""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        return jsonify({'status': 'error', 'message': '找不到會議記錄'}), 404

    if not meeting['supplementary_file_path']:
        return jsonify({'status': 'error', 'message': '此會議沒有輔助文件'}), 400

    file_path = meeting['supplementary_file_path']
    if not Path(file_path).exists():
        return jsonify({'status': 'error', 'message': '輔助文件檔案遺失'}), 404

    try:
        # 1. 讀取文件內容
        document_text = read_document_text(file_path)
        if not document_text:
            return jsonify({'status': 'success', 'message': '文件內容為空，無需處理'})

        # 2. 呼叫 OpenAI 產生摘要
        client = current_app.audio_processor.openai_client
        prompt = f"""
        你是一個專業的會議助理。請閱讀以下文件內容，並為其產生一份簡潔的摘要，提煉出最重要的核心重點。
        摘要應包含：
        1.  文件的主要目的或主題。
        2.  關鍵的論點、數據或發現。
        3.  任何重要的結論或建議。

        摘要內容請以條列式呈現，力求精簡扼要，總長度不要超過 300 字。

        文件內容如下：
        ---
        {document_text[:8000]}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一個專業的會議助理。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
        )
        summary = response.choices[0].message.content

        # 3. 儲存摘要到資料庫
        update_supplementary_summary(meeting_id, summary)

        return jsonify({'status': 'success', 'summary': summary})

    except ValueError as e:
        logger.warning(f"處理輔助文件失敗 (會議 ID: {meeting_id}): {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        logger.error(f"處理輔助文件時發生未知錯誤 (會議 ID: {meeting_id}): {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '伺服器內部錯誤'}), 500

# ===============================================
# 字幕與逐字稿 API
# ===============================================

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
        # 獲取發言者名稱映射
        speaker_names = get_speaker_names(meeting_id)
        segments = parse_srt_content(content, speaker_names)
        return jsonify({
            'meeting_id': meeting_id,
            'total_segments': len(segments),
            'segments': segments
        })
    return result # 這是錯誤回應

@bp.route('/meeting/<meeting_id>/transcription')
def get_meeting_transcription(meeting_id):
    """API: 獲取會議逐字稿"""
    try:
        meeting = get_meeting_by_id(meeting_id)
        if not meeting:
            return jsonify({'status': 'error', 'message': '找不到指定的會議記錄'}), 404
        
        if meeting['status'] != 'completed' or not meeting['speaker_srt_path']:
            return jsonify({'status': 'error', 'message': '會議逐字稿尚未生成'}), 400
            
        srt_file_path = current_app.config['BASE_DIR'] / meeting['speaker_srt_path']
        if not srt_file_path.exists():
            return jsonify({'status': 'error', 'message': '逐字稿檔案不存在'}), 404
        
        with open(srt_file_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        
        # 獲取發言者名稱映射
        speaker_names = get_speaker_names(meeting_id)
        
        # 使用字幕處理函數解析內容
        segments = parse_srt_content(srt_content, speaker_names)
        
        return jsonify({
            'status': 'success',
            'data': {
                'segments': segments,
                'srt_content': srt_content,
                'transcription_text': _parse_srt_to_transcription(srt_content),
                'speaker_names': speaker_names
            }
        })
        
    except Exception as e:
        logger.error(f"獲取會議逐字稿時發生錯誤: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': '獲取逐字稿時發生錯誤'}), 500

def _parse_srt_to_transcription(srt_content):
    """將 SRT 格式轉換為逐字稿格式"""
    lines = srt_content.strip().split('\n')
    transcription_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 跳過序號行
        if line.isdigit():
            i += 1
            continue
            
        # 跳過時間戳行
        if '-->' in line:
            i += 1
            continue
            
        # 跳過空行
        if not line:
            i += 1
            continue
            
        # 這是字幕內容行
        transcription_lines.append(line)
        i += 1
    
    return '\n'.join(transcription_lines)

# ===============================================
# AI 摘要功能 API
# ===============================================

@bp.route('/meeting/<meeting_id>/summary', methods=['GET'])
def get_meeting_summary_api(meeting_id):
    """API: 獲取會議摘要"""
    summary = get_meeting_summary(meeting_id)
    if summary:
        # 檢查 from_cache 參數
        from_cache = request.args.get('from_cache', 'true').lower() == 'true'
        return jsonify({
            'status': 'success',
            'data': summary,
            'from_cache': from_cache
        })
    else:
        return jsonify({
            'status': 'not_found',
            'message': '此會議的摘要不存在或尚未生成'
        }), 404

@bp.route('/meeting/<meeting_id>/generate-summary', methods=['POST'])
def generate_meeting_summary(meeting_id):
    """API: 為會議生成或重新生成 AI 摘要"""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        return jsonify({'status': 'error', 'message': '找不到會議記錄'}), 404
        
    if meeting['status'] != 'completed':
        return jsonify({'status': 'error', 'message': '會議尚未處理完成'}), 400

    # 獲取逐字稿
    try:
        with (current_app.config['BASE_DIR'] / meeting['speaker_srt_path']).open('r', encoding='utf-8') as f:
            srt_content = f.read()
        transcription_text = _parse_srt_to_transcription(srt_content)
        if not transcription_text:
            raise FileNotFoundError("無法從 SRT 檔案中提取逐字稿內容。")
    except (FileNotFoundError, TypeError) as e:
        logger.error(f"無法讀取或解析會議 {meeting_id} 的逐字稿: {e}")
        return jsonify({'status': 'error', 'message': '找不到或無法解析逐字稿內容'}), 404

    try:
        # 獲取發言者名稱映射和輔助文件摘要
        speaker_names = get_speaker_names(meeting_id)
        supplementary_summary = meeting.get('supplementary_summary')

        # 準備發送給 OpenAI 的提示
        prompt = create_summary_prompt(
            transcription_text,
            speaker_names,
            supplementary_summary
        )
        
        # 呼叫 OpenAI API
        client = current_app.audio_processor.openai_client
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一個專業的會議記錄員，擅長從逐字稿中提取摘要、行動項目和關鍵重點。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.5
        )
        
        summary_json = response.choices[0].message.content
        parsed_summary = parse_summary_from_json(summary_json)
        
        # 處理 action_items
        action_items_str = "\n".join(f"- {item}" for item in parsed_summary.get("action_items", []))
        final_summary = parsed_summary.get('summary', '')
        if action_items_str:
            final_summary += "\n\n**行動項目:**\n" + action_items_str

        save_meeting_summary(
            meeting_id,
            global_summary=final_summary,
            chunk_summaries=None,
            speaker_highlights=parsed_summary.get('speaker_highlights')
        )
        
        new_summary = get_meeting_summary(meeting_id)
        return jsonify({'status': 'success', 'summary': new_summary})

    except Exception as e:
        logger.error(f"生成摘要時發生錯誤 (會議 ID: {meeting_id}): {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': f'生成摘要失敗: {str(e)}'}), 500

# ===============================================
# 發言者管理 API
# ===============================================

@bp.route('/meeting/<meeting_id>/speaker-names', methods=['GET'])
def get_speaker_names_api(meeting_id):
    """API: 獲取會議的發言者名稱映射"""
    try:
        speaker_names = get_speaker_names(meeting_id)
        return jsonify({
            'status': 'success',
            'speaker_names': speaker_names
        })
    except Exception as e:
        logger.error(f"獲取發言者名稱時發生錯誤: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '獲取發言者名稱失敗'
        }), 500

@bp.route('/meeting/<meeting_id>/speaker-names', methods=['POST'])
def update_speaker_name_api(meeting_id):
    """API: 更新發言者名稱"""
    try:
        data = request.get_json()
        
        if not data or 'original_speaker_id' not in data or 'custom_name' not in data:
            return jsonify({
                'status': 'error',
                'message': '缺少必要參數'
            }), 400
        
        original_speaker_id = data['original_speaker_id']
        custom_name = data['custom_name'].strip()
        
        if not custom_name:
            return jsonify({
                'status': 'error',
                'message': '發言者名稱不能為空'
            }), 400
        
        update_speaker_name(meeting_id, original_speaker_id, custom_name)
        
        return jsonify({
            'status': 'success',
            'message': '發言者名稱更新成功'
        })
    
    except Exception as e:
        logger.error(f"更新發言者名稱時發生錯誤: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '更新發言者名稱失敗'
        }), 500

@bp.route('/meeting/<meeting_id>/speaker-names/<original_speaker_id>', methods=['DELETE'])
def delete_speaker_name_api(meeting_id, original_speaker_id):
    """API: 刪除發言者名稱映射，恢復原始名稱"""
    try:
        delete_speaker_name(meeting_id, original_speaker_id)
        
        return jsonify({
            'status': 'success',
            'message': '發言者名稱已恢復為原始名稱'
        })
    
    except Exception as e:
        logger.error(f"刪除發言者名稱映射時發生錯誤: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': '恢復原始名稱失敗'
        }), 500
