"""
說話者辨識測試模組（使用 pyannote/speaker-diarization-3.1）

此模組用於測試 pyannote.audio 的說話者辨識功能。
可以獨立運行以驗證說話者辨識是否正常工作。
"""

import sys
import os
import argparse
import logging
import subprocess
from dotenv import load_dotenv
from pyannote.audio import Pipeline
import torch

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def convert_to_wav_if_needed(audio_path: str) -> str:
    """
    如果是 .m4a 檔案，自動轉換為 .wav
    """
    if audio_path.lower().endswith(".m4a"):
        wav_path = os.path.splitext(audio_path)[0] + ".wav"
        if not os.path.exists(wav_path):
            logger.info(f"偵測到 .m4a 檔案，使用 ffmpeg 轉換為 .wav: {wav_path}")
            try:
                subprocess.run(["ffmpeg", "-y", "-i", audio_path, wav_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                logger.error("ffmpeg 轉換失敗，請確認是否已安裝 ffmpeg。")
                sys.exit(1)
        return wav_path
    return audio_path

def test_diarization(audio_path: str, num_speakers: int = None):
    """
    測試說話者辨識功能
    
    Args:
        audio_path: 音訊檔案路徑
        num_speakers: 預期的說話者數量（可選）
    """
    load_dotenv()
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        logger.error("未設置 HF_TOKEN，請建立 .env 並添加 HF_TOKEN=your_token")
        return

    if not os.path.exists(audio_path):
        logger.error(f"找不到音訊檔案: {audio_path}")
        return

    audio_path = convert_to_wav_if_needed(audio_path)

    try:
        logger.info("載入 pyannote.audio 說話者辨識模型（3.1）...")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )

        if torch.cuda.is_available():
            logger.info("使用 GPU 進行說話者辨識")
            pipeline.to(torch.device("cuda"))
        else:
            logger.info("使用 CPU 進行說話者辨識")

        logger.info(f"開始辨識音訊檔案: {audio_path}")
        if num_speakers:
            logger.info(f"指定說話者數量: {num_speakers}")
            diarization = pipeline(audio_path, num_speakers=num_speakers)
        else:
            diarization = pipeline(audio_path)

        logger.info("說話者辨識結果：")
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            logger.info(f"start={turn.start:.1f}s stop={turn.end:.1f}s speaker_{speaker}")

        logger.info("辨識完成")

    except Exception as e:
        logger.error(f"辨識過程中發生錯誤: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="測試 pyannote.audio 說話者辨識 (3.1)")
    parser.add_argument("audio_path", help="音訊檔案路徑（支援 .wav / .m4a）")
    parser.add_argument("--num_speakers", type=int, help="預期說話者數量（可選）")
    args = parser.parse_args()
    test_diarization(args.audio_path, args.num_speakers)
