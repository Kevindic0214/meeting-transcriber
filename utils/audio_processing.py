import os
import subprocess
import logging
from pathlib import Path
from openai import OpenAI
from pyannote.audio import Pipeline
import torch
import srt

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self, hf_token: str, openai_client: OpenAI):
        self.hf_token = hf_token
        self.openai_client = openai_client
        self.diarization_pipeline = None

    def _init_diarization_model(self):
        """延遲初始化語者辨識模型"""
        if self.diarization_pipeline is None:
            logger.info("載入 pyannote.audio 語者辨識模型...")
            self.diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self.hf_token
            )
            if torch.cuda.is_available():
                logger.info("使用 GPU 進行語者辨識")
                self.diarization_pipeline.to(torch.device("cuda"))
            else:
                logger.info("使用 CPU 進行語者辨識")

    def get_audio_duration(self, input_path: Path) -> float:
        """取得音訊檔案長度（秒）"""
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

    def _get_bitrate_by_duration(self, seconds: float) -> str:
        """根據音訊長度決定壓縮位元率"""
        if seconds <= 1800:  # 30分鐘以內
            return "64k"
        elif seconds <= 3600:  # 1小時以內
            return "48k"
        else:  # 超過1小時
            return "32k"

    def compress_audio(self, input_path: Path, output_path: Path) -> float:
        """壓縮音訊檔案為適合 Whisper 處理的格式"""
        duration = self.get_audio_duration(input_path)
        bitrate = self._get_bitrate_by_duration(duration)
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-ac", "1", "-ar", "16000",
            "-c:a", "libopus", "-b:a", bitrate,
            str(output_path)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"壓縮完成: {output_path.name} (位元率: {bitrate})")
        return duration

    def convert_to_wav(self, input_path: Path, output_path: Path):
        """轉換音訊為 WAV 格式供語者辨識使用"""
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-ac", "1", "-ar", "16000",
            str(output_path)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"已轉換為 wav: {output_path.name}")

    def transcribe_audio(self, audio_path: Path) -> str:
        """使用 Whisper API 進行語音轉文字"""
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="srt"
                )
            return transcript
        except Exception as e:
            logger.error(f"Whisper 轉錄失敗 [{audio_path}]: {e}")
            return ""

    def diarize_audio(self, audio_path: Path, rttm_output_path: Path, num_speakers: int = None):
        """執行語者辨識"""
        try:
            logger.info(f"開始語者辨識: {audio_path.name}")
            self._init_diarization_model()
            
            if num_speakers and num_speakers > 0:
                diarization = self.diarization_pipeline(str(audio_path), num_speakers=num_speakers)
            else:
                diarization = self.diarization_pipeline(str(audio_path))
                
            with open(rttm_output_path, "w", encoding="utf-8") as f:
                diarization.write_rttm(f)
            logger.info(f"RTTM 已儲存: {rttm_output_path.name}")
            return diarization
        except Exception as e:
            logger.error(f"語者辨識失敗 [{audio_path}]: {e}")
            raise e

    def parse_rttm(self, rttm_path: Path):
        """解析 RTTM 檔案，提取語者時間片段"""
        segments = []
        with open(rttm_path, encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 9: 
                    continue
                start = float(parts[3])
                dur = float(parts[4])
                speaker = parts[7]
                segments.append({'start': start, 'end': start + dur, 'speaker': speaker})
        return segments

    def _find_best_speaker(self, seg_start: float, seg_end: float, diarization_segments: list) -> str:
        """根據重疊時間找出字幕段落對應的主要語者"""
        best, best_overlap = None, 0.0
        for d in diarization_segments:
            overlap_start = max(seg_start, d['start'])
            overlap_end = min(seg_end, d['end'])
            overlap = max(0.0, overlap_end - overlap_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best = d['speaker']
        return best or "unknown"

    def merge_srt_with_speakers(self, srt_path: Path, rttm_path: Path, output_path: Path):
        """合併字幕和語者資訊"""
        diarization = self.parse_rttm(rttm_path)
        
        with open(srt_path, encoding='utf-8') as f:
            subs = list(srt.parse(f.read()))
        
        new_subs = []
        for sub in subs:
            start_sec = sub.start.total_seconds()
            end_sec = sub.end.total_seconds()
            speaker = self._find_best_speaker(start_sec, end_sec, diarization)
            
            speaker_display = speaker.replace("SPEAKER_", "發言者")
            sub.content = f"[{speaker_display}]: {sub.content}"
            new_subs.append(sub)
        
        result = srt.compose(new_subs)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
        logger.info(f"已輸出結合語者的字幕：{output_path}") 