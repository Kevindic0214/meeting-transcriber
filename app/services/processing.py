import logging
import shutil
from pathlib import Path
from datetime import datetime
import queue

from flask import current_app

from app.db import update_meeting_status

logger = logging.getLogger(__name__)

def process_meeting(app, meeting_id, file_path_str, num_speakers=None):
    """
    處理會議音訊的主要函式。
    此函式在獨立的執行緒中運行，需要傳入 app context。
    """
    with app.app_context():
        progress_tracker = current_app.progress_tracker
        progress_queue = queue.Queue()
        progress_tracker[meeting_id] = progress_queue

        def report_progress(step, progress, message):
            """輔助函式，用於回報進度"""
            logger.info(f"會議 {meeting_id} 進度: {message} ({progress}%)")
            progress_queue.put({'step': step, 'progress': progress, 'message': message})

        try:
            logger.info(f"開始處理會議 {meeting_id}")
            
            # 從 app context 獲取相依性
            audio_processor = current_app.audio_processor
            config = current_app.config
            
            file_path = Path(file_path_str)
            
            # 更新狀態為處理中
            update_meeting_status(meeting_id, 'processing')
            
            # 從設定檔定義輸出路徑
            base_name = file_path.stem
            compressed_path = config['PROCESSED_FOLDER'] / f"{meeting_id}.webm"
            wav_path = config['PROCESSED_FOLDER'] / f"{meeting_id}.wav"
            srt_path = config['OUTPUT_FOLDER'] / f"{meeting_id}.srt"
            rttm_path = config['OUTPUT_FOLDER'] / f"{meeting_id}.rttm"
            speaker_srt_path = config['OUTPUT_FOLDER'] / f"{meeting_id}_speaker.srt"
            
            # 步驟 1: 音訊預處理
            report_progress('preprocessing', 10, '音訊預處理中...')
            if file_path.suffix.lower() != ".webm":
                duration = audio_processor.compress_audio(file_path, compressed_path)
                audio_processor.convert_to_wav(file_path, wav_path)
            else:
                shutil.copy(file_path, compressed_path)
                duration = audio_processor.get_audio_duration(file_path)
                audio_processor.convert_to_wav(file_path, wav_path)
            report_progress('preprocessing', 25, '音訊預處理完成')

            # 步驟 2: Whisper 轉錄
            report_progress('transcription', 30, '開始語音轉文字...')
            
            # 檢查壓縮後的檔案大小是否超過 OpenAI 限制 (25MB)
            whisper_file_size_mb = compressed_path.stat().st_size / (1024 * 1024)
            if whisper_file_size_mb > 25:
                error_msg = f"壓縮後的音檔大小 ({whisper_file_size_mb:.2f}MB) 超過 Whisper API 25MB 的限制。"
                logger.error(f"會議 {meeting_id}: {error_msg}")
                raise Exception(error_msg)

            srt_text = audio_processor.transcribe_audio(compressed_path)
            if not srt_text:
                raise Exception("Whisper 轉錄失敗，可能原因為 API 金鑰錯誤、網路問題或音檔內容為靜音。")
            
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_text)
            report_progress('transcription', 60, '語音轉文字完成')

            # 步驟 3: 語者辨識
            report_progress('diarization', 65, '開始語者辨識...')
            audio_processor.diarize_audio(wav_path, rttm_output_path=rttm_path, num_speakers=num_speakers)
            
            diarization_segments = audio_processor.parse_rttm(rttm_path)
            speakers = set(seg['speaker'] for seg in diarization_segments)
            actual_num_speakers = len(speakers)
            report_progress('diarization', 85, '語者辨識完成')
            
            # 步驟 4: 合併字幕和語者資訊
            report_progress('merge', 90, '合併字幕與語者資訊...')
            audio_processor.merge_srt_with_speakers(srt_path, rttm_path, speaker_srt_path)
            
            # 更新為完成狀態
            base_dir = config['BASE_DIR']
            update_meeting_status(
                meeting_id, 
                'completed',
                processed_at=datetime.now().isoformat(),
                duration=duration,
                num_speakers=actual_num_speakers,
                srt_path=str(srt_path.relative_to(base_dir)),
                rttm_path=str(rttm_path.relative_to(base_dir)),
                speaker_srt_path=str(speaker_srt_path.relative_to(base_dir))
            )
            report_progress('completed', 100, '處理完成！')
            
            logger.info(f"會議 {meeting_id} 處理完成")
            
        except Exception as e:
            logger.error(f"處理會議 {meeting_id} 失敗: {e}", exc_info=True)
            # 這個更新也會在 app context 中運行
            update_meeting_status(meeting_id, 'failed', error_message=str(e))
            progress_queue.put({'step': 'failed', 'progress': 100, 'message': str(e)})
        finally:
            # 發送結束信號並清理
            progress_queue.put({'status': 'done'})
            if meeting_id in progress_tracker:
                del progress_tracker[meeting_id]
                logger.info(f"已清理會議 {meeting_id} 的進度追蹤器。")
