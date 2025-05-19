import openai
import os
import logging
import torch
from typing import List, Dict, Any
from dotenv import load_dotenv
import tempfile
from pydub import AudioSegment
import io
from pyannote.audio import Pipeline
import numpy as np

# 載入環境變數
load_dotenv()
openai_api_key = os.getenv('OPENAI_API_KEY')
huggingface_token = os.getenv('HF_TOKEN')
if not openai_api_key:
    raise ValueError("請設置OPENAI_API_KEY環境變數")
if not huggingface_token:
    raise ValueError("請設置HF_TOKEN環境變數，用於pyannote.audio模型")

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 載入pyannote.audio說話者辨識模型
try:
    diarization_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.0",
        use_auth_token=huggingface_token)
    
    # 如果有GPU，使用GPU加速
    if torch.cuda.is_available():
        logger.info("使用GPU進行說話者辨識")
        diarization_pipeline.to(torch.device("cuda"))
    else:
        logger.info("使用CPU進行說話者辨識")
except Exception as e:
    logger.warning(f"無法載入說話者辨識模型: {str(e)}")
    diarization_pipeline = None

def process_audio(file_path: str) -> List[Dict[str, Any]]:
    """
    處理音訊文件，使用OpenAI API進行轉寫並結合pyannote.audio進行說話者辨識
    
    Args:
        file_path: 音訊文件路徑
        
    Returns:
        包含轉寫和說話者信息的分段列表
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"音訊文件不存在: {file_path}")
            
        logger.info(f"開始處理音訊文件: {file_path}")
        
        # 檢查文件大小，OpenAI API限制為25MB
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 25:
            logger.info(f"文件大小 ({file_size_mb:.2f}MB) 超過OpenAI API限制，進行文件壓縮和分段處理")
            segments = process_large_audio(file_path)
        else:
            # 設置OpenAI API密鑰
            client = openai.OpenAI(api_key=openai_api_key)
            
            # 開啟音訊文件
            logger.info("進行語音轉寫...")
            with open(file_path, "rb") as audio_file:
                # 使用OpenAI API進行轉寫
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
                
            logger.info("語音轉寫完成")
            
            # 將OpenAI回應轉換為與原格式兼容的格式
            segments = []
            for i, seg in enumerate(response.segments):
                segment = {
                    "id": i,
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "speaker": "未知"  # 初始設置為未知，稍後會更新
                }
                segments.append(segment)
                
                logger.debug(f"[Segment {i:02d}] {seg.start:.2f}s → {seg.end:.2f}s 文字：{seg.text}")
        
        # 使用pyannote.audio進行說話者辨識
        if diarization_pipeline is not None:
            logger.info("進行說話者辨識...")
            try:
                # 進行說話者辨識
                diarization_result = diarization_pipeline(file_path)
                
                # 將說話者辨識結果匹配到語音段落
                assign_speakers_to_segments(segments, diarization_result)
                
                logger.info("說話者辨識完成")
            except Exception as e:
                logger.error(f"說話者辨識失敗: {str(e)}")
                # 若說話者辨識失敗，保持原有的「未知」標籤
        else:
            logger.warning("說話者辨識模型未載入，跳過說話者辨識步驟")
        
        logger.info("音訊處理完成")
        return segments
        
    except Exception as e:
        logger.error(f"音訊處理過程發生錯誤: {str(e)}")
        raise

def process_large_audio(file_path: str) -> List[Dict[str, Any]]:
    """
    處理大型音訊文件，分割成小段後用OpenAI API處理
    
    Args:
        file_path: 音訊文件路徑
        
    Returns:
        合併後的分段列表
    """
    try:
        # 讀取音訊文件
        audio = AudioSegment.from_file(file_path)
        
        # 分割成10分鐘片段 (OpenAI建議的最大長度)
        segment_length = 10 * 60 * 1000  # 10分鐘，以毫秒為單位
        
        all_segments = []
        client = openai.OpenAI(api_key=openai_api_key)
        segment_offset = 0  # 記錄全局時間偏移
        
        for i, start in enumerate(range(0, len(audio), segment_length)):
            # 切割音訊片段
            chunk = audio[start:start + segment_length]
            
            # 創建臨時文件
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_filename = temp_file.name
                chunk.export(temp_filename, format="mp3")
            
            logger.info(f"處理第 {i+1} 個音訊片段...")
            
            # 使用OpenAI API處理這個片段
            with open(temp_filename, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            
            # 調整片段的時間戳記，加上全局偏移
            segment_time_offset = start / 1000.0  # 轉換為秒
            
            # 轉換回與原格式兼容的格式
            for j, seg in enumerate(response.segments):
                segment = {
                    "id": len(all_segments) + j,
                    "start": seg.start + segment_time_offset,
                    "end": seg.end + segment_time_offset,
                    "text": seg.text,
                    "speaker": "未知"  # 初始設置為未知，稍後會更新
                }
                all_segments.append(segment)
            
            # 刪除臨時文件
            os.unlink(temp_filename)
            
            # 更新偏移
            segment_offset += len(chunk) / 1000.0
        
        # 對大型音訊文件也進行說話者辨識
        if diarization_pipeline is not None:
            logger.info("對完整音訊進行說話者辨識...")
            try:
                diarization_result = diarization_pipeline(file_path)
                assign_speakers_to_segments(all_segments, diarization_result)
                logger.info("說話者辨識完成")
            except Exception as e:
                logger.error(f"說話者辨識失敗: {str(e)}")
        
        return all_segments
    
    except Exception as e:
        logger.error(f"分割處理音訊時發生錯誤: {str(e)}")
        raise

def assign_speakers_to_segments(segments: List[Dict[str, Any]], diarization_result) -> None:
    """
    將pyannote.audio的說話者辨識結果匹配到Whisper的轉寫段落
    
    Args:
        segments: Whisper API轉寫的段落列表
        diarization_result: pyannote.audio的說話者辨識結果
    """
    # 根據重疊情況為每個段落分配說話者
    for i, segment in enumerate(segments):
        segment_start = segment["start"]
        segment_end = segment["end"]
        
        # 找出與當前段落重疊最多的說話者
        max_overlap = 0
        best_speaker = None
        
        # pyannote.audio返回的是一個標註對象，可以通過迭代訪問說話者和時間段
        for turn, _, speaker in diarization_result.itertracks(yield_label=True):
            spk_start = turn.start
            spk_end = turn.end
            
            # 計算重疊部分
            overlap_start = max(segment_start, spk_start)
            overlap_end = min(segment_end, spk_end)
            
            if overlap_end > overlap_start:  # 有重疊
                overlap_duration = overlap_end - overlap_start
                if overlap_duration > max_overlap:
                    max_overlap = overlap_duration
                    best_speaker = speaker
        
        # 將最佳匹配的說話者分配給段落
        if best_speaker is not None:
            segment["speaker"] = f"說話者_{best_speaker}"
        # 若沒有找到匹配的說話者，保持「未知」標籤