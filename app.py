#!/usr/bin/env python3
"""
會議助手網站 - Flask + Gentelella
整合 Whisper ASR + pyannote 語者辨識
"""
import os
import sys
import uuid
import json
import subprocess
import shutil
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import srt
from datetime import timedelta

from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
from threading import Thread
import sqlite3
from flask_moment import Moment

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

if __name__ == '__main__':
    # 初始化資料庫
    init_db()
    
    # 確保資料夾存在
    ensure_folders()
    
    # 啟動開發伺服器
    app.run(debug=True, host='0.0.0.0', port=5000)