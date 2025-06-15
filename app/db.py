import sqlite3
import logging
from datetime import datetime

from flask import current_app, g

logger = logging.getLogger(__name__)

def custom_convert_timestamp(val):
    """
    將資料庫中的時間戳轉換為 datetime 物件。
    為避免錯誤，此函式會處理多種格式。
    """
    if val is None:
        return None

    val_str = val.decode('utf-8')

    # 常見格式
    formats_to_try = [
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]

    for fmt in formats_to_try:
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue

    # 最後嘗試使用 fromisoformat 處理帶有 'T' 的格式
    try:
        return datetime.fromisoformat(val_str)
    except ValueError:
        pass

    logger.warning(f"無法解析時間戳: {val_str}")
    return val_str  # 如果所有解析都失敗，則以字串形式返回

sqlite3.register_converter("timestamp", custom_convert_timestamp)

def get_db():
    """
    為當前的 application context 打開一個新的資料庫連線(如果還沒有的話)。
    """
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DB_PATH'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        # 讓查詢結果可以像字典一樣透過欄位名稱存取
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """關閉請求結束時的資料庫連線。"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """初始化資料庫綱要 (schema)。"""
    try:
        # 這裡不使用 get_db() 因為我們希望在應用程式啟動時獨立執行
        db = sqlite3.connect(current_app.config['DB_PATH'])
        cursor = db.cursor()
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
        db.commit()
        db.close()
        logger.info("資料庫已初始化。")
    except Exception as e:
        logger.error(f"無法初始化資料庫: {e}")

def add_meeting(meeting_id, filename, original_filename):
    """新增一筆新的會議記錄到資料庫。"""
    sql = 'INSERT INTO meetings (id, filename, original_filename, status) VALUES (?, ?, ?, ?)'
    conn = get_db()
    conn.execute(sql, (meeting_id, filename, original_filename, 'uploaded'))
    conn.commit()

def get_meeting_by_id(meeting_id):
    """透過 ID 獲取一筆會議記錄。"""
    sql = 'SELECT * FROM meetings WHERE id = ?'
    cursor = get_db().execute(sql, (meeting_id,))
    return cursor.fetchone()

def get_all_meetings():
    """獲取所有會議記錄，依建立時間降序排列。"""
    sql = 'SELECT * FROM meetings ORDER BY created_at DESC'
    cursor = get_db().execute(sql)
    return cursor.fetchall()

def update_meeting_status(meeting_id, status, **kwargs):
    """更新會議的狀態和其他詳細資訊。"""
    conn = get_db()
    
    update_fields = ['status = ?']
    params = [status]
    
    for key, value in kwargs.items():
        if value is not None:
            update_fields.append(f'{key} = ?')
            params.append(value)
    
    params.append(meeting_id)
    
    sql = f"UPDATE meetings SET {', '.join(update_fields)} WHERE id = ?"
    conn.execute(sql, params)
    conn.commit()

def delete_meeting_by_id(meeting_id):
    """透過 ID 從資料庫刪除一筆會議記錄。"""
    sql = 'DELETE FROM meetings WHERE id = ?'
    conn = get_db()
    conn.execute(sql, (meeting_id,))
    conn.commit()

def init_app(app):
    """
    向 Flask app 註冊資料庫函式。這會由應用程式工廠呼叫。
    """
    # 註冊 teardown 函式，在每個請求結束後自動關閉資料庫連線
    app.teardown_appcontext(close_db)
