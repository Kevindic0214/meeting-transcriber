import os
import sys
import logging
from flask import Flask
from flask_moment import Moment
from openai import OpenAI
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue

from config import Config
from utils.audio_processing import AudioProcessor

# 將擴充套件實例化在全域範圍，但不在這裡初始化
moment = Moment()

def create_app(config_class=Config):
    """應用程式工廠函式"""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # 設定日誌
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # 設置全域進度追蹤器
    app.progress_tracker = {}

    # 檢查 HuggingFace Token 是否存在
    if not app.config['HF_TOKEN']:
        logger.error("未設置 HF_TOKEN，請在 .env 檔案中添加 HF_TOKEN=your_token")
        sys.exit(1)
        
    # 檢查 OpenAI API Key 是否存在
    if not os.getenv('OPENAI_API_KEY'):
        logger.error("未設置 OPENAI_API_KEY，請在 .env 檔案中添加 OPENAI_API_KEY=your_key")
        sys.exit(1)

    # 初始化 Flask 擴充套件
    moment.init_app(app)

    # 初始化資料庫
    from . import db
    db.init_app(app) # 註冊 close_db 等函式
    with app.app_context():
        # 確保資料庫表格已建立
        db.init_db()

    # 初始化音訊處理器並附加到 app
    client = OpenAI()
    app.audio_processor = AudioProcessor(
        hf_token=app.config['HF_TOKEN'],
        openai_client=client
    )

    # 確保所有必要的資料夾都存在
    # 由於此邏輯位於應用程式工廠中，它只會在啟動時執行一次。
    try:
        folders_to_check = [
            app.config['UPLOADS_FOLDER'],
            app.config['PROCESSED_FOLDER'],
            app.config['OUTPUT_FOLDER']
        ]
        for folder in folders_to_check:
            folder.mkdir(parents=True, exist_ok=True)
        logger.info("所有必要的資料夾都已確認存在。")
    except OSError as e:
        logger.error(f"建立資料夾失敗: {e}", exc_info=True)
        sys.exit(1)

    # 註冊藍圖
    from .main import bp as main_bp
    app.register_blueprint(main_bp)

    from .api import bp as api_bp
    app.register_blueprint(api_bp)

    logger.info("Flask 應用程式已建立並設定完成。")

    return app
