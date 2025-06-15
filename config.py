import os
from pathlib import Path
from dotenv import load_dotenv

# 載入 .env 檔案中的環境變數
load_dotenv()

class Config:
    """基礎設定類別"""

    # 專案根目錄
    BASE_DIR = Path(__file__).parent.resolve()

    # 用於 session 管理的密鑰
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')

    # 最大上傳檔案大小 (500MB)
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024

    # HuggingFace API Token
    HF_TOKEN = os.getenv("HF_TOKEN")

    # 資料庫檔案路徑
    DB_PATH = BASE_DIR / "meeting_assistant.db"

    # 資料夾路徑設定
    UPLOADS_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    PROCESSED_FOLDER = BASE_DIR / "app" / "static" / "processed"
    OUTPUT_FOLDER = BASE_DIR / "app" / "static" / "output"
