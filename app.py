#!/usr/bin/env python3
"""
會議助手網站 - Flask + Gentelella
整合 Whisper ASR + pyannote 語者辨識
"""
import logging
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from threading import Thread

import srt
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_moment import Moment
from openai import OpenAI
from werkzeug.utils import secure_filename

from utils.audio_processing import AudioProcessor

# 專案根目錄
BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "meeting_assistant.db"

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 載入環境變數
load_dotenv()

# 初始化 Flask 應用
app = Flask(__name__)
moment = Moment(app)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB 檔案大小限制

# OpenAI 和 HuggingFace 設定
client = OpenAI()
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    logger.error("未設置 HF_TOKEN，請建立 .env 並添加 HF_TOKEN=your_token")
    sys.exit(1)

# 初始化音訊處理器
audio_processor = AudioProcessor(hf_token=HF_TOKEN, openai_client=client)

# 資料庫初始化
def init_db():
    """初始化SQLite資料庫"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 創建會議記錄表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            duration REAL,
            num_speakers INTEGER,
            srt_path TEXT,
            rttm_path TEXT,
            speaker_srt_path TEXT,
            error_message TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# 確保必要的資料夾存在
def ensure_folders():
    """確保所有需要的資料夾都存在"""
    folders = {
        'uploads': BASE_DIR / "static" / "uploads",
        'processed': BASE_DIR / "static" / "processed", 
        'output': BASE_DIR / "static" / "output"
    }
    
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    return folders

def update_meeting_status(meeting_id, status, **kwargs):
    """更新會議處理狀態"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 構建動態更新語句
    update_fields = ['status = ?']
    params = [status]
    
    for key, value in kwargs.items():
        if value is not None:
            update_fields.append(f'{key} = ?')
            params.append(value)
    
    params.append(meeting_id)  # WHERE 條件的參數
    
    sql = f"UPDATE meetings SET {', '.join(update_fields)} WHERE id = ?"
    cursor.execute(sql, params)
    conn.commit()
    conn.close()

def process_meeting_async(meeting_id, file_path, num_speakers=None):
    """非同步處理會議音訊的主要函數"""
    try:
        folders = ensure_folders()
        audio_file = Path(file_path)
        
        # 更新狀態為處理中
        update_meeting_status(meeting_id, 'processing')
        
        # 建立輸出檔案路徑
        base_name = audio_file.stem
        compressed_path = folders['processed'] / f"{meeting_id}.webm"
        wav_path = folders['processed'] / f"{meeting_id}.wav"
        srt_path = folders['output'] / f"{meeting_id}.srt"
        rttm_path = folders['output'] / f"{meeting_id}.rttm"
        speaker_srt_path = folders['output'] / f"{meeting_id}_speaker.srt"
        
        # 步驟1: 音訊預處理
        logger.info(f"開始處理會議 {meeting_id}: 音訊預處理")
        if audio_file.suffix.lower() != ".webm":
            duration = audio_processor.compress_audio(audio_file, compressed_path)
            audio_processor.convert_to_wav(audio_file, wav_path)
        else:
            shutil.copy(audio_file, compressed_path)
            duration = audio_processor.get_audio_duration(audio_file)
            audio_processor.convert_to_wav(audio_file, wav_path)
        
        # 步驟2: Whisper 轉錄
        logger.info(f"會議 {meeting_id}: 開始語音轉文字")
        srt_text = audio_processor.transcribe_audio(compressed_path)
        if not srt_text:
            raise Exception("Whisper 轉錄失敗")
        
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_text)
        
        # 步驟3: 語者辨識
        logger.info(f"會議 {meeting_id}: 開始語者辨識")
        audio_processor.diarize_audio(wav_path, rttm_output_path=rttm_path, num_speakers=num_speakers)
        
        # 計算語者數量
        diarization_segments = audio_processor.parse_rttm(rttm_path)
        speakers = set(seg['speaker'] for seg in diarization_segments)
        actual_num_speakers = len(speakers)
        
        # 步驟4: 合併字幕和語者資訊
        logger.info(f"會議 {meeting_id}: 合併字幕和語者資訊")
        audio_processor.merge_srt_with_speakers(srt_path, rttm_path, speaker_srt_path)
        
        # 更新為完成狀態
        update_meeting_status(
            meeting_id, 
            'completed',
            processed_at=datetime.now().isoformat(),
            duration=duration,
            num_speakers=actual_num_speakers,
            srt_path=str(srt_path.relative_to(BASE_DIR)),
            rttm_path=str(rttm_path.relative_to(BASE_DIR)),
            speaker_srt_path=str(speaker_srt_path.relative_to(BASE_DIR))
        )
        
        logger.info(f"會議 {meeting_id} 處理完成")
        
    except Exception as e:
        logger.error(f"會議 {meeting_id} 處理失敗: {e}")
        update_meeting_status(meeting_id, 'failed', error_message=str(e))

# Web 路由定義
@app.route('/')
def index():
    """首頁 - 顯示上傳介面"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """處理檔案上傳"""
    if 'file' not in request.files:
        flash('沒有選擇檔案', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('沒有選擇檔案', 'error')
        return redirect(url_for('index'))
    
    # 檢查檔案類型
    allowed_extensions = {'.m4a', '.mp3', '.wav', '.flac', '.webm'}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        flash('不支援的檔案格式', 'error')
        return redirect(url_for('index'))
    
    # 儲存檔案
    folders = ensure_folders()
    meeting_id = str(uuid.uuid4())
    filename = secure_filename(f"{meeting_id}_{file.filename}")
    file_path = folders['uploads'] / filename
    file.save(file_path)
    
    # 獲取語者數量設定（可選）
    num_speakers = request.form.get('num_speakers')
    if num_speakers and num_speakers.isdigit():
        num_speakers = int(num_speakers)
    else:
        num_speakers = None
    
    # 記錄到資料庫
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO meetings (id, filename, original_filename, status)
        VALUES (?, ?, ?, ?)
    ''', (meeting_id, filename, file.filename, 'uploaded'))
    conn.commit()
    conn.close()
    
    # 啟動非同步處理
    thread = Thread(target=process_meeting_async, args=(meeting_id, file_path, num_speakers))
    thread.daemon = True
    thread.start()
    
    flash('檔案上傳成功，正在處理中...', 'success')
    return redirect(url_for('meeting_detail', meeting_id=meeting_id))

@app.route('/meetings')
def meetings_list():
    """會議列表頁面"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, original_filename, status, created_at, duration, num_speakers
        FROM meetings 
        ORDER BY created_at DESC
    ''')
    meetings = cursor.fetchall()
    conn.close()
    
    # 轉換為字典格式方便模板使用
    meetings_data = []
    for meeting in meetings:
        meetings_data.append({
            'id': meeting[0],
            'original_filename': meeting[1],
            'status': meeting[2],
            'created_at': meeting[3],
            'duration': meeting[4],
            'num_speakers': meeting[5]
        })
    
    return render_template('meetings.html', meetings=meetings_data)

@app.route('/meeting/<meeting_id>')
def meeting_detail(meeting_id):
    """會議詳情頁面"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM meetings WHERE id = ?', (meeting_id,))
    meeting = cursor.fetchone()
    conn.close()
    
    if not meeting:
        flash('找不到指定的會議記錄', 'error')
        return redirect(url_for('meetings_list'))
    
    # 轉換為字典格式
    meeting_data = {
        'id': meeting[0],
        'filename': meeting[1],
        'original_filename': meeting[2],
        'status': meeting[3],
        'created_at': meeting[4],
        'processed_at': meeting[5],
        'duration': meeting[6],
        'num_speakers': meeting[7],
        'srt_path': meeting[8],
        'rttm_path': meeting[9],
        'speaker_srt_path': meeting[10],
        'error_message': meeting[11]
    }
    
    return render_template('meeting_detail.html', meeting=meeting_data)

@app.route('/api/meeting/<meeting_id>/status')
def get_meeting_status(meeting_id):
    """API: 獲取會議處理狀態"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT status, error_message FROM meetings WHERE id = ?', (meeting_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return jsonify({'status': result[0], 'error_message': result[1]})
    else:
        return jsonify({'status': 'not_found'}), 404

@app.route('/download/<meeting_id>/<file_type>')
def download_file(meeting_id, file_type):
    """下載處理結果檔案"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 根據檔案類型選擇對應的欄位
    field_map = {
        'srt': 'srt_path',
        'rttm': 'rttm_path', 
        'speaker_srt': 'speaker_srt_path'
    }
    
    if file_type not in field_map:
        return "不支援的檔案類型", 400
    
    cursor.execute(f'SELECT {field_map[file_type]}, original_filename FROM meetings WHERE id = ?', (meeting_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return "檔案不存在", 404
    
    file_path = BASE_DIR / result[0]
    if not file_path.exists():
        return "檔案不存在", 404
    
    # 構建下載檔名
    original_name = Path(result[1]).stem
    extension_map = {
        'srt': '.srt',
        'rttm': '.rttm',
        'speaker_srt': '_語者標註.srt'
    }
    
    download_name = f"{original_name}{extension_map[file_type]}"
    
    return send_file(file_path, as_attachment=True, download_name=download_name)

@app.route('/api/meeting/<meeting_id>/subtitle')
def get_meeting_subtitle(meeting_id):
    """
    獲取會議字幕內容用於網頁顯示
    
    這個端點的設計目的是為前端提供字幕內容，讓用戶可以在瀏覽器中
    直接閱讀、搜尋和互動，而不是下載檔案到本地。
    """
    try:
        # 建立資料庫連接並查詢會議記錄
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 查詢會議的字幕檔案路徑和處理狀態
        cursor.execute('''
            SELECT speaker_srt_path, status, original_filename 
            FROM meetings 
            WHERE id = ?
        ''', (meeting_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        # 檢查會議記錄是否存在
        if not result:
            logger.warning(f"會議記錄不存在: {meeting_id}")
            return jsonify({
                'error': '會議記錄不存在',
                'code': 'MEETING_NOT_FOUND'
            }), 404
        
        speaker_srt_path, status, original_filename = result
        
        # 檢查會議是否已處理完成
        if status != 'completed':
            logger.info(f"會議 {meeting_id} 尚未處理完成，當前狀態: {status}")
            return jsonify({
                'error': '會議尚未處理完成',
                'code': 'PROCESSING_NOT_COMPLETE',
                'current_status': status
            }), 400
        
        # 檢查字幕檔案路徑是否存在
        if not speaker_srt_path:
            logger.error(f"會議 {meeting_id} 的字幕檔案路徑為空")
            return jsonify({
                'error': '字幕檔案路徑不存在',
                'code': 'SUBTITLE_PATH_MISSING'
            }), 404
        
        # 構建完整的檔案路徑
        subtitle_file = BASE_DIR / speaker_srt_path
        
        # 檢查檔案是否實際存在於檔案系統中
        if not subtitle_file.exists():
            logger.error(f"字幕檔案不存在於檔案系統: {subtitle_file}")
            return jsonify({
                'error': '字幕檔案遺失',
                'code': 'SUBTITLE_FILE_MISSING',
                'file_path': str(subtitle_file)
            }), 404
        
        # 讀取字幕檔案內容
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                subtitle_content = f.read()
            
            # 記錄成功的字幕載入
            logger.info(f"成功載入會議 {meeting_id} 的字幕內容，檔案大小: {len(subtitle_content)} 字元")
            
            # 返回字幕內容，設定正確的 Content-Type
            # 這裡我們返回純文字，讓前端可以直接處理和顯示
            return subtitle_content, 200, {
                'Content-Type': 'text/plain; charset=utf-8',
                'X-Meeting-ID': meeting_id,
                'X-Original-Filename': original_filename
            }
            
        except UnicodeDecodeError as e:
            # 處理編碼錯誤，可能是檔案編碼不是 UTF-8
            logger.error(f"字幕檔案編碼錯誤: {e}")
            try:
                # 嘗試使用其他編碼讀取
                with open(subtitle_file, 'r', encoding='utf-8-sig') as f:
                    subtitle_content = f.read()
                return subtitle_content, 200, {
                    'Content-Type': 'text/plain; charset=utf-8'
                }
            except Exception as e2:
                logger.error(f"使用備用編碼讀取檔案也失敗: {e2}")
                return jsonify({
                    'error': '字幕檔案編碼錯誤',
                    'code': 'ENCODING_ERROR'
                }), 500
        
        except IOError as e:
            # 處理檔案讀取錯誤（權限問題、磁碟錯誤等）
            logger.error(f"讀取字幕檔案 IO 錯誤: {e}")
            return jsonify({
                'error': '讀取字幕檔案失敗',
                'code': 'FILE_READ_ERROR'
            }), 500
    
    except sqlite3.Error as e:
        # 處理資料庫錯誤
        logger.error(f"資料庫查詢錯誤: {e}")
        return jsonify({
            'error': '資料庫查詢失敗',
            'code': 'DATABASE_ERROR'
        }), 500
    
    except Exception as e:
        # 處理其他未預期的錯誤
        logger.error(f"獲取字幕內容時發生未知錯誤: {e}")
        return jsonify({
            'error': '伺服器內部錯誤',
            'code': 'INTERNAL_ERROR'
        }), 500


@app.route('/api/meeting/<meeting_id>/subtitle/formatted')
def get_meeting_subtitle_formatted(meeting_id):
    """
    獲取格式化的會議字幕內容
    
    這個端點提供更結構化的字幕資料，包含時間戳記、語者資訊等，
    方便前端進行更豐富的顯示和互動功能。
    """
    try:
        # 首先獲取原始字幕內容
        subtitle_response = get_meeting_subtitle(meeting_id)
        
        # 如果原始字幕獲取失敗，直接返回錯誤
        if isinstance(subtitle_response, tuple) and subtitle_response[1] != 200:
            return subtitle_response
        
        # 提取字幕內容（如果是成功的響應）
        if isinstance(subtitle_response, tuple):
            subtitle_content = subtitle_response[0]
        else:
            subtitle_content = subtitle_response
        
        # 解析 SRT 格式的字幕
        subtitle_segments = parse_srt_content(subtitle_content)
        
        # 返回結構化的 JSON 資料
        return jsonify({
            'meeting_id': meeting_id,
            'total_segments': len(subtitle_segments),
            'segments': subtitle_segments
        })
    
    except Exception as e:
        logger.error(f"獲取格式化字幕時發生錯誤: {e}")
        return jsonify({
            'error': '獲取格式化字幕失敗',
            'code': 'FORMATTING_ERROR'
        }), 500


def parse_srt_content(srt_content):
    """
    解析 SRT 格式的字幕內容，轉換為結構化資料
    
    這個函數將原始的 SRT 文字內容解析成包含時間戳記、語者資訊
    和文字內容的結構化資料，方便前端進行各種處理和顯示。
    """
    try:
        # 使用 srt 函式庫解析內容
        subtitles = list(srt.parse(srt_content))
        
        segments = []
        for subtitle in subtitles:
            # 提取語者資訊（如果存在）
            speaker = extract_speaker_from_content(subtitle.content)
            
            # 清理內容文字（移除語者標籤）
            clean_content = clean_subtitle_content(subtitle.content)
            
            segment = {
                'index': subtitle.index,
                'start_time': subtitle.start.total_seconds(),
                'end_time': subtitle.end.total_seconds(),
                'start_time_formatted': format_time(subtitle.start.total_seconds()),
                'end_time_formatted': format_time(subtitle.end.total_seconds()),
                'duration': (subtitle.end - subtitle.start).total_seconds(),
                'speaker': speaker,
                'content': clean_content,
                'original_content': subtitle.content
            }
            segments.append(segment)
        
        return segments
    
    except Exception as e:
        logger.error(f"解析 SRT 內容時發生錯誤: {e}")
        return []


def extract_speaker_from_content(content):
    """
    從字幕內容中提取語者資訊
    
    這個修正版本能夠正確處理你實際的語者標籤格式，
    包括數字編號的語者標籤（如 [發言者00]、[發言者01] 等）
    """
    import re
    
    # 擴展的語者標籤匹配模式，涵蓋更多實際使用的格式
    speaker_patterns = [
        # 數字格式的語者標籤（你的實際格式）
        r'\[發言者(\d+)\]',       # [發言者00], [發言者01], [發言者02] 等
        r'\[語者(\d+)\]',         # [語者00], [語者01] 等
        r'\[Speaker(\d+)\]',      # [Speaker00], [Speaker01] 等
        r'\[SPEAKER_(\d+)\]',     # [SPEAKER_00], [SPEAKER_01] 等（原始 pyannote 格式）
        
        # 字母格式的語者標籤（備用支援）
        r'\[發言者([A-Z])\]',     # [發言者A], [發言者B] 等
        r'\[Speaker ([A-Z])\]',   # [Speaker A], [Speaker B] 等
        r'\[語者([A-Z])\]',       # [語者A], [語者B] 等
        r'\[([A-Z])\]',           # [A], [B] 等
        
        # 冒號格式的語者標籤
        r'發言者(\d+):',          # 發言者00:, 發言者01: 等
        r'語者(\d+):',            # 語者00:, 語者01: 等
        r'Speaker(\d+):',         # Speaker00:, Speaker01: 等
        r'發言者([A-Z]):',        # 發言者A:, 發言者B: 等
        r'Speaker ([A-Z]):',      # Speaker A:, Speaker B: 等
        
        # 空格格式的語者標籤（新增）
        r'\[發言者(\d+)\] ',      # [發言者00] , [發言者01]  等
        r'\[語者(\d+)\] ',        # [語者00] , [語者01]  等
        r'\[Speaker(\d+)\] ',     # [Speaker00] , [Speaker01]  等
        r'\[SPEAKER_\d+\]\s*',    # [SPEAKER_00] , [SPEAKER_01]  等
        r'\[發言者([A-Z])\] ',    # [發言者A] , [發言者B]  等
        r'\[Speaker ([A-Z])\] ',  # [Speaker A] , [Speaker B]  等
        r'\[語者([A-Z])\] ',      # [語者A] , [語者B]  等
        r'\[([A-Z])\] ',          # [A] , [B]  等
    ]
    
    for pattern in speaker_patterns:
        match = re.search(pattern, content)
        if match:
            speaker_id = match.group(1)
            
            # 處理數字格式的語者ID
            if speaker_id.isdigit():
                # 將數字轉換為更友善的顯示格式
                speaker_number = int(speaker_id)
                # 你可以選擇保持數字格式或轉換為字母格式
                return f"發言者{speaker_number:02d}"  # 保持數字格式：發言者00, 發言者01
                # 或者使用下面這行轉換為字母格式：
                # return f"發言者{chr(65 + speaker_number)}"  # 轉換為：發言者A, 發言者B
            else:
                # 處理字母格式的語者ID
                return f"發言者{speaker_id}"
    
    # 如果沒有匹配到任何模式，嘗試更寬鬆的匹配
    # 這是為了處理一些邊緣情況或格式變異
    fallback_patterns = [
        r'(\d+):', # 純數字後跟冒號，如 "00:", "01:"
        r'([A-Z]):', # 純字母後跟冒號，如 "A:", "B:"
    ]
    
    for pattern in fallback_patterns:
        match = re.search(pattern, content)
        if match:
            speaker_id = match.group(1)
            if speaker_id.isdigit():
                return f"發言者{int(speaker_id):02d}"
            else:
                return f"發言者{speaker_id}"
    
    # 如果完全無法識別，返回基於內容位置的預設值
    # 這比直接返回"未知"更有用
    return "發言者未識別"


def clean_subtitle_content(content):
    """
    清理字幕內容，移除語者標籤和時間戳記
    
    這個函數專注於移除實際使用的語者標籤格式，
    確保清理後的內容只包含純粹的對話文字。
    """
    import re
    
    # 需要移除的語者標籤模式（根據實際 SRT 檔案格式優化）
    patterns_to_remove = [
        # 最常見的格式，帶冒號的語者標籤
        r'\[發言者\d+\]:\s*',      # [發言者00]: , [發言者01]:  等
        r'\[語者\d+\]:\s*',        # [語者00]: , [語者01]:  等
        r'\[Speaker\d+\]:\s*',     # [Speaker00]: , [Speaker01]:  等
        r'\[SPEAKER_\d+\]:\s*',    # [SPEAKER_00]: , [SPEAKER_01]:  等
        
        # 不帶冒號的語者標籤格式（新格式）
        r'\[發言者\d+\]\s+',       # [發言者00] , [發言者01]  等
        r'\[語者\d+\]\s+',         # [語者00] , [語者01]  等
        r'\[Speaker\d+\]\s+',      # [Speaker00] , [Speaker01]  等
        r'\[SPEAKER_\d+\]\s+',     # [SPEAKER_00] , [SPEAKER_01]  等
        
        # 可能的時間戳記格式
        r'\(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}\)\s*',  # (00:01:23 - 00:02:45)
        r'\[\d{2}:\d{2}:\d{2}\]\s*',  # [00:01:23]
    ]
    
    cleaned = content
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned)
    
    # 移除多餘的空白和換行
    cleaned = re.sub(r'\n+', '\n', cleaned)  # 合併多個換行
    cleaned = re.sub(r'\s+', ' ', cleaned)   # 合併多個空格
    
    return cleaned.strip()


def format_time(seconds):
    """將秒數格式化為 HH:MM:SS 或 MM:SS"""
    if not isinstance(seconds, (int, float)):
        return "00:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

@app.route('/api/meeting/<meeting_id>/delete', methods=['DELETE'])
def delete_meeting(meeting_id):
    """API: 刪除指定的會議記錄及其相關檔案"""
    try:
        # 1. 從資料庫獲取會議資訊
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
        meeting = cursor.fetchone()

        if not meeting:
            conn.close()
            return jsonify({'status': 'error', 'message': '會議記錄不存在'}), 404

        # 將查詢結果映射到字典
        columns = [desc[0] for desc in cursor.description]
        meeting_data = dict(zip(columns, meeting))
        
        # 2. 刪除相關檔案
        folders = ensure_folders()
        
        # 刪除上傳的原始檔案
        if meeting_data.get('filename'):
            uploaded_file = folders['uploads'] / meeting_data['filename']
            if uploaded_file.exists():
                uploaded_file.unlink()
                logger.info(f"已刪除上傳檔案: {uploaded_file}")

        # 刪除處理過程中的檔案 (webm, wav)
        processed_webm = folders['processed'] / f"{meeting_id}.webm"
        if processed_webm.exists():
            processed_webm.unlink()
            logger.info(f"已刪除處理檔案: {processed_webm}")
            
        processed_wav = folders['processed'] / f"{meeting_id}.wav"
        if processed_wav.exists():
            processed_wav.unlink()
            logger.info(f"已刪除處理檔案: {processed_wav}")

        # 刪除輸出結果檔案 (srt, rttm, etc.)
        for path_key in ['srt_path', 'rttm_path', 'speaker_srt_path']:
            if meeting_data.get(path_key):
                output_file = BASE_DIR / meeting_data[path_key]
                if output_file.exists():
                    output_file.unlink()
                    logger.info(f"已刪除輸出檔案: {output_file}")
        
        # 3. 從資料庫刪除會議記錄
        cursor.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        conn.commit()
        conn.close()
        
        logger.info(f"已成功刪除會議記錄: {meeting_id}")
        return jsonify({'status': 'success', 'message': '會議記錄已成功刪除'})

    except sqlite3.Error as e:
        logger.error(f"刪除會議時發生資料庫錯誤 (ID: {meeting_id}): {e}")
        return jsonify({'status': 'error', 'message': '資料庫錯誤'}), 500
    except Exception as e:
        logger.error(f"刪除會議時發生未知錯誤 (ID: {meeting_id}): {e}")
        return jsonify({'status': 'error', 'message': '伺服器內部錯誤'}), 500


# 主程式入口
if __name__ == "__main__":
    init_db()  # 確保資料庫和表格已建立
    ensure_folders() # 確保資料夾存在
    app.run(debug=True, host='0.0.0.0', port=8080)