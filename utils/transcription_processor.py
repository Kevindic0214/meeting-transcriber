import re
from collections import defaultdict
from openai import AzureOpenAI
from config import Config

# --- 初始化 OpenAI 用戶端 ---
try:
    client = AzureOpenAI(
        api_key=Config.AZURE_OPENAI_KEY,
        api_version=Config.AZURE_OPENAI_API_VERSION,
        azure_endpoint=Config.AZURE_OPENAI_ENDPOINT,
    )
    # 測試連線 (可選，但建議)
    client.models.list()
    print("Azure OpenAI client initialized successfully.")
except Exception as e:
    print(f"Error initializing Azure OpenAI client: {e}")
    client = None

def _get_llm_response(prompt: str, model: str = Config.AZURE_OPENAI_MODEL) -> str:
    """
    向 OpenAI API 發送請求並獲取回應。

    Args:
        prompt (str): 發送給模型的提示。
        model (str): 要使用的模型名稱。

    Returns:
        str: 模型生成的回應內容。
    """
    if not client:
        raise ConnectionError("Azure OpenAI client is not initialized. Please check your credentials in the .env file.")
        
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant specialized in summarizing and analyzing meeting transcripts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1024,
            top_p=0.95,
            frequency_penalty=0.2,
            presence_penalty=0.1
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"An error occurred while communicating with OpenAI: {e}")
        return ""

def _chunk_transcription(transcription: str, chunk_size: int = 10) -> list[str]:
    """
    將逐字稿按發言次數切分為多個片段。

    Args:
        transcription (str): 完整的會議逐字稿。
        chunk_size (int): 每個片段包含的發言數量。

    Returns:
        list[str]: 切分後的逐字稿片段列表。
    """
    lines = transcription.strip().split('\n')
    chunks = []
    for i in range(0, len(lines), chunk_size):
        chunk_content = "\n".join(lines[i:i + chunk_size])
        chunks.append(chunk_content)
    return chunks

def _summarize_chunks(chunks: list[str]) -> list[str]:
    """
    對每個逐字稿片段生成摘要。

    Args:
        chunks (list[str]): 逐字稿片段列表。

    Returns:
        list[str]: 每個片段的摘要列表。
    """
    chunk_summaries = []
    prompt_template = "以下是會議片段，請用一至兩句總結這段內容：\n\n---\n{chunk}\n---"
    
    for i, chunk in enumerate(chunks):
        print(f"Summarizing chunk {i+1}/{len(chunks)}...")
        prompt = prompt_template.format(chunk=chunk)
        summary = _get_llm_response(prompt)
        if summary:
            chunk_summaries.append(summary)
    
    return chunk_summaries

def _generate_global_summary(chunk_summaries: list[str]) -> str:
    """
    將所有片段摘要統整為一份完整的會議總結。

    Args:
        chunk_summaries (list[str]): 片段摘要列表。

    Returns:
        str: 完整的會議總結。
    """
    print("Generating global summary...")
    combined_summaries = "\n".join(chunk_summaries)
    prompt = f"以下是多段會議片段的摘要，請將它們整理成一段流暢且完整的會議摘要，內容需涵蓋所有重點，並限制在300字以內：\n\n---\n{combined_summaries}\n---"
    
    return _get_llm_response(prompt)

def _generate_speaker_highlights(transcription: str) -> list[str]:
    """
    針對每位發言者生成重點摘要。

    Args:
        transcription (str): 完整的會議逐字稿。

    Returns:
        list[str]: 每位發言者的重點摘要列表。
    """
    print("Generating speaker highlights...")
    lines = transcription.strip().split('\n')
    speaker_dialogue = defaultdict(list)

    # 使用正則表達式解析 "[發言者XX]："
    speaker_pattern = re.compile(r"^\[(.*?)\]\s*[:：]")

    for line in lines:
        match = speaker_pattern.match(line)
        if match:
            # speaker現在是group(1)，也就是方括號內的內容
            speaker = match.group(1).strip() + "：" # 統一加上全形冒號以便後續處理
            content = line[len(match.group(0)):].strip()
            speaker_dialogue[speaker].append(content)
        else:
            # 如果某一行沒有發言人標籤，可以將其歸類或忽略
            # 這裡我們暫時忽略
            pass


    speaker_highlights = []
    
    for speaker, dialogues in speaker_dialogue.items():
        print(f"Generating highlights for {speaker}...")
        full_dialogue = "\n".join(dialogues)
        # 移除冒號以符合 prompt 格式要求
        speaker_name = speaker.replace('：', '')
        prompt = f"這是「{speaker_name}」在會議中的所有發言內容，請從中整理出 3-5 條最重要的發言重點，若沒有重點，請回傳「{speaker_name} 本次會議中無重要發言」。請按照以下格式輸出，每個重點以分號分隔：\n{speaker_name}：重點1；重點2；重點3；...；\n\n---\n{full_dialogue}\n---"
        
        highlight = _get_llm_response(prompt)
        if highlight:
            speaker_highlights.append(highlight)

    # --- 偵錯用 ---
    print(f"【偵錯】最終的發言人重點列表: {speaker_highlights}")
    # --- 偵錯結束 ---
            
    return speaker_highlights

def create_summary_prompt(transcription: str, speaker_names: dict, supplementary_summary: str = None) -> str:
    """
    創建一個用於生成會議摘要的完整提示。

    Args:
        transcription (str): 會議逐字稿。
        speaker_names (dict): 發言者 ID 和名稱的對應字典。
        supplementary_summary (str, optional): 輔助文件的摘要。

    Returns:
        str: 完整的提示內容。
    """
    prompt = f"""
請根據以下會議逐字稿和相關資訊，生成一份詳細的會議記錄。

**會議逐字稿:**
---
{transcription}
---

**發言者列表:**
{', '.join(speaker_names.values()) if speaker_names else '未知'}

"""
    if supplementary_summary:
        prompt += f"""
**輔助文件摘要:**
---
{supplementary_summary}
---
"""
    prompt += """
**輸出要求:**
請以 JSON 格式輸出，包含以下三個鍵：
1.  `"summary"`: (字串) 一段約 200-300 字的會議摘要，總結會議的背景、討論的關鍵點、以及最終的結論或共識。
2.  `"action_items"`: (字串陣列) 列出會議中明確提到的待辦事項，每一項都應清楚說明負責人（如果有的話）和任務內容。如果沒有，請返回一個空陣列 `[]`。
3.  `"speaker_highlights"`: (物件陣列) 針對每一位發言者，整理其最重要的 1-3 個發言重點。每個物件應包含 `"speaker"` (發言者名稱) 和 `"highlights"` (字串陣列) 兩個鍵。

請確保 JSON 格式正確無誤。
"""
    return prompt

def parse_summary_from_json(json_string: str) -> dict:
    """
    從 OpenAI 回傳的 JSON 字串中解析出摘要資訊。

    Args:
        json_string (str): OpenAI 回傳的 JSON 格式字串。

    Returns:
        dict: 包含 'summary' 和 'speaker_highlights' 的字典。
    """
    import json
    try:
        data = json.loads(json_string)
        # 為了相容舊的 save_meeting_summary 函式，我們主要提取這兩部分
        return {
            "summary": data.get("summary", ""),
            "action_items": data.get("action_items", []),
            "speaker_highlights": data.get("speaker_highlights", [])
        }
    except json.JSONDecodeError:
        # 如果解析失敗，返回一個預設結構，並將原始字串放在 summary 中
        return {
            "summary": "無法解析 AI 回應，原始內容如下：\n" + json_string,
            "action_items": [],
            "speaker_highlights": []
        }

def process_transcription(transcription: str, chunk_size: int = 15) -> tuple[str, str, list[str]]:
    """
    處理會議逐字稿，生成全局摘要和發言人重點。

    Args:
        transcription (str): 會議逐字稿內容。
        chunk_size (int): 切分逐字稿時，每個片段的發言行數。

    Returns:
        tuple[str, str, list[str]]: 包含 (全局摘要, 所有片段摘要的字串, 發言人重點列表) 的元組。
    """
    if not isinstance(transcription, str) or not transcription.strip():
        return "無效的逐字稿輸入。", "", []

    # 1. 將逐字稿切成多個片段
    chunks = _chunk_transcription(transcription, chunk_size)
    
    # 2. 對每個片段生成摘要
    chunk_summaries = _summarize_chunks(chunks)
    
    # 3. 統整成會議總結
    global_summary = _generate_global_summary(chunk_summaries)
    
    # 4. 生成每位發言者的重點
    speaker_highlights = _generate_speaker_highlights(transcription)

    # 將片段摘要列表轉換為一個字串以便顯示
    chunk_summaries_str = "\n".join(f"- {s}" for s in chunk_summaries)
    
    return global_summary, chunk_summaries_str, speaker_highlights 