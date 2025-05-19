import whisperx
import torch
import os
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv
# 載入環境變數
load_dotenv()
auth_token = os.getenv('HF_TOKEN')
if not auth_token:
    raise ValueError("請設置HF_TOKEN環境變數")

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 確定設備
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"使用設備: {device}")

def process_audio(file_path: str) -> List[Dict[str, Any]]:
    """
    處理音訊文件，進行轉寫和說話者分離
    
    Args:
        file_path: 音訊文件路徑
        
    Returns:
        包含轉寫和說話者信息的分段列表
    """
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"音訊文件不存在: {file_path}")
            
        logger.info(f"開始處理音訊文件: {file_path}")
        
        # 載入模型
        logger.info("載入轉寫模型...")
        model = whisperx.load_model("large-v2", device)
        
        # 語音轉寫
        logger.info("進行語音轉寫...")
        audio = whisperx.load_audio(file_path)
        result = model.transcribe(audio, batch_size=8)
        
        # 釋放轉寫模型內存
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
            
        # 說話者分離
        logger.info("進行說話者分離...")
        try:
            diarize_model = whisperx.DiarizationPipeline(use_auth_token=auth_token, device=device)
            diarize_segments = diarize_model(audio)
            
            # 對齊時間戳記
            logger.info("對齊時間戳記...")
            result = whisperx.assign_word_speakers(diarize_segments, result)
            
            logger.debug("===== 說話者辨識結果 =====")
            for i, seg in enumerate(result["segments"]):
                # WhisperX 的 segment 通常包含 start, end, speaker, text
                start = seg.get("start", None)
                end = seg.get("end", None)
                speaker = seg.get("speaker", "未知")
                text = seg.get("text", "").replace("\n", " ")
                logger.debug(
                    f"[Segment {i:02d}] {start:.2f}s → {end:.2f}s  說話人：{speaker}  文字：{text}"
                )
            logger.debug("===== 說話者辨識結束 =====")
            
            # 釋放說話者分離模型內存
            del diarize_model
            if device == "cuda":
                torch.cuda.empty_cache()
                
        except Exception as e:
            logger.error(f"說話者分離失敗: {str(e)}")
            # 如果說話者分離失敗，返回未分離的轉寫結果
            for i, segment in enumerate(result["segments"]):
                segment["speaker"] = "未知"
            
        logger.info("音訊處理完成")
        return result["segments"]
        
    except Exception as e:
        logger.error(f"音訊處理過程發生錯誤: {str(e)}")
        raise