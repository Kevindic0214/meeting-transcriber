import os
import logging
from typing import List, Dict, Tuple, Any
from collections import defaultdict
from dotenv import load_dotenv
import openai

# 載入環境變數
load_dotenv()

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Azure OpenAI 設定
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

openai.api_type = "azure"
openai.api_key = AZURE_API_KEY
openai.api_base = AZURE_ENDPOINT
openai.api_version = AZURE_API_VERSION

# Prompt 模板
CHUNK_SUMMARY_PROMPT = """
[會議錄音片段]
{chunk_text}

使用一至兩句話生成此片段的摘要。
"""

GLOBAL_SUMMARY_PROMPT = """
[片段摘要集合]
{summaries}

基於以上片段摘要生成完整會議摘要，字數不超過500字。
"""

SPEAKER_HIGHLIGHT_PROMPT = """
[發言人 {speaker} 文本]
{speaker_text}

請提煉其中 3~5 條關鍵重點，並以「- {speaker}：重點1；重點2；重點3」格式回覆。
如果發言人沒有發言，不用輸出任何內容。
"""

# 分段大小，可根據需要調整
CHUNK_SIZE = 10


def generate_tasks(transcription: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    多階段處理：
      1. 將轉寫分段 CHUNK_SIZE 切塊，對每塊做局部摘要。
      2. 基於所有局部摘要生成全局會議摘要。
      3. 針對每位發言者彙整其所有發言並獨立提煉重點。

    Args:
        transcription: 轉寫分段列表，包含 'speaker' 與 'text'.
    Returns:
        (會議摘要, 發言者重點) 的 Tuple
    """
    try:
        if not transcription:
            logger.warning("轉寫列表為空，無法生成任務")
            return "無有效轉寫內容", "無發言者重點"

        # 1. 分段局部摘要
        chunk_summaries = []
        for idx in range(0, len(transcription), CHUNK_SIZE):
            chunk = transcription[idx: idx + CHUNK_SIZE]
            chunk_lines = []
            for seg in chunk:
                text = seg.get('text', '').strip()
                speaker = seg.get('speaker', '未知')
                if text:
                    chunk_lines.append(f"發言人{speaker}: {text}")
            if not chunk_lines:
                continue
            chunk_text = "\n".join(chunk_lines)
            prompt = CHUNK_SUMMARY_PROMPT.format(chunk_text=chunk_text)
            logger.info(f"生成第 {len(chunk_summaries)+1} 段局部摘要...")
            resp = openai.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[{'role':'user', 'content': prompt}],
                temperature=0.3,
                max_tokens=500
            )
            summary = resp.choices[0].message.content.strip()
            chunk_summaries.append(summary)

        if not chunk_summaries:
            logger.warning("無任何局部摘要，無法生成全局摘要")
            global_summary = "無法生成會議摘要"
        else:
            # 2. 全局摘要
            summaries_text = "\n".join([f"片段{i+1}: {s}" for i, s in enumerate(chunk_summaries)])
            prompt = GLOBAL_SUMMARY_PROMPT.format(summaries=summaries_text)
            logger.info("生成全局會議摘要...")
            resp = openai.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[{'role':'user','content':prompt}],
                temperature=0.5,
                max_tokens=700
            )
            global_summary = resp.choices[0].message.content.strip()

        # 3. 發言者重點提煉
        by_speaker = defaultdict(list)
        for seg in transcription:
            text = seg.get('text', '').strip()
            speaker = seg.get('speaker', '未知')
            if text:
                by_speaker[speaker].append(text)

        speaker_highlights = []
        for speaker, texts in by_speaker.items():
            speaker_text = "\n".join(texts)
            prompt = SPEAKER_HIGHLIGHT_PROMPT.format(speaker=speaker, speaker_text=speaker_text)
            logger.info(f"提煉發言人 {speaker} 重點...")
            resp = openai.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[{'role':'user','content':prompt}],
                temperature=0.5,
                max_tokens=300
            )
            points = resp.choices[0].message.content.strip()
            speaker_highlights.append(points)

        highlights = "\n".join(speaker_highlights)
        return global_summary, highlights

    except Exception as e:
        logger.error(f"生成任務時出錯: {e}")
        return f"錯誤：{e}", f"錯誤：{e}"
