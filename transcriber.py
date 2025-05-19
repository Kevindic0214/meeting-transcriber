#!/usr/bin/env python3
"""
音訊批次處理整合：Whisper ASR + pyannote 語者辨識
"""
import os
import sys
import subprocess
import shutil
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from pyannote.audio import Pipeline
import torch

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 載入環境變數
load_dotenv()
# 初始化 OpenAI 客戶端
client = OpenAI()
# 讀取 Hugging Face Token
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    logger.error("未設置 HF_TOKEN，請建立 .env 並添加 HF_TOKEN=your_token")
    sys.exit(1)

# 初始化語者辨識模型
logger.info("載入 pyannote.audio 語者辨識模型 ...")
diarization_pipeline = Pipeline.from_pretrained(
    "pyannote/speaker-diarization-3.1",
    use_auth_token=HF_TOKEN
)
if torch.cuda.is_available():
    logger.info("使用 GPU 進行語者辨識")
    diarization_pipeline.to(torch.device("cuda"))
else:
    logger.info("使用 CPU 進行語者辨識")

def ensure_folders():
    """確保所有需要的資料夾都存在"""
    base_dir = Path.cwd()
    uploads_folder = base_dir / "uploads"
    processed_folder = base_dir / "processed"
    output_folder = base_dir / "output"
    uploads_folder.mkdir(exist_ok=True)
    processed_folder.mkdir(exist_ok=True)
    output_folder.mkdir(exist_ok=True)
    return uploads_folder, processed_folder, output_folder

def get_bitrate_by_duration(seconds):
    if seconds <= 1800:
        return "64k"
    elif seconds <= 3600:
        return "48k"
    else:
        return "32k"

def get_audio_duration(input_path: Path) -> float:
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            str(input_path)
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        return float(result.stdout)
    except Exception as e:
        logger.error(f"無法取得音檔長度 [{input_path}]: {e}")
        return 0.0

def compress_audio(input_path: Path, output_path: Path):
    duration = get_audio_duration(input_path)
    bitrate = get_bitrate_by_duration(duration)
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ac", "1", "-ar", "16000",
        "-c:a", "libopus", "-b:a", bitrate,
        str(output_path)
    ]
    subprocess.run(cmd, check=True)
    logger.info(f"壓縮完成: {output_path.name} (位元率: {bitrate})")

def convert_to_wav(input_path: Path, output_path: Path):
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ac", "1", "-ar", "16000",
        str(output_path)
    ]
    subprocess.run(cmd, check=True)
    logger.info(f"已轉換為 wav: {output_path.name}")

def transcribe_audio(audio_path: Path) -> str:
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="srt"
            )
        return transcript
    except Exception as e:
        logger.error(f"Whisper 轉錄失敗 [{audio_path}]: {e}")
        return ""

def save_transcript(text: str, output_path: Path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info(f"SRT 已儲存: {output_path.name}")

def diarize_audio(audio_path: Path, rttm_output_path: Path = None, num_speakers: int = None):
    """
    語者辨識，輸出 RTTM。
    """
    try:
        logger.info(f"開始語者辨識: {audio_path.name}")
        if num_speakers:
            diarization = diarization_pipeline(str(audio_path), num_speakers=num_speakers)
        else:
            diarization = diarization_pipeline(str(audio_path))
        if rttm_output_path:
            with open(rttm_output_path, "w", encoding="utf-8") as f:
                diarization.write_rttm(f)
            logger.info(f"RTTM 已儲存: {rttm_output_path.name}")
        return diarization
    except Exception as e:
        logger.error(f"語者辨識失敗 [{audio_path}]: {e}")

def process_audio_files():
    uploads_folder, processed_folder, output_folder = ensure_folders()
    logger.info(f"處理上傳資料夾: {uploads_folder.resolve()}")
    audio_extensions = [".m4a", ".mp3", ".wav", ".flac", ".webm"]
    found = False
    for audio_file in sorted(uploads_folder.iterdir()):
        if not audio_file.is_file() or audio_file.suffix.lower() not in audio_extensions:
            continue
        found = True
        base_name = audio_file.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_basename = f"{base_name}_{timestamp}"
        compressed_path = processed_folder / f"{output_basename}.webm"
        wav_path = processed_folder / f"{output_basename}.wav"
        srt_path = output_folder / f"{output_basename}.srt"
        rttm_path = output_folder / f"{output_basename}.rttm"
        # 壓縮與轉 wav
        if audio_file.suffix.lower() != ".webm":
            logger.info(f"壓縮: {audio_file.name} → {compressed_path.name}")
            compress_audio(audio_file, compressed_path)
            logger.info(f"轉 wav: {audio_file.name} → {wav_path.name}")
            convert_to_wav(audio_file, wav_path)
        else:
            shutil.copy(audio_file, compressed_path)
            logger.info(f"複製 webm: {compressed_path.name}")
            convert_to_wav(audio_file, wav_path)
        # Whisper 轉錄
        logger.info(f"Whisper 轉錄: {compressed_path.name}")
        srt_text = transcribe_audio(compressed_path)
        if srt_text:
            save_transcript(srt_text, srt_path)
        # 語者辨識
        diarize_audio(wav_path, rttm_output_path=rttm_path)
        # 移動原始檔
        processed_original = processed_folder / f"original_{audio_file.name}"
        shutil.move(audio_file, processed_original)
        logger.info(f"已移動原始檔: {processed_original.name}")
    if not found:
        logger.info("未找到支援的音訊檔。")

if __name__ == "__main__":
    process_audio_files()
