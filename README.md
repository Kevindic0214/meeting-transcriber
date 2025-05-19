# 會議錄音轉錄系統

這是一個使用 OpenAI Whisper API 進行會議錄音轉錄和分析的系統，結合了 pyannote.audio 進行說話者辨識。

## 功能

- 語音轉文字：使用 OpenAI Whisper API 進行高品質的語音轉錄
- 說話者辨識：使用 pyannote.audio 進行說話者分離和標識
- 會議摘要：自動生成會議的摘要
- 發言者待辦事項：根據每位參與者的發言內容提取待辦事項

## 更新日誌

### 2023-05-20
- 添加了 pyannote.audio 進行說話者辨識
- 整合了 Whisper API 轉錄結果與說話者辨識結果

### 2023-05-19
- 更改了語音轉錄服務：從本地模型轉為使用 OpenAI Whisper API
- 添加了對大型音訊檔案的分段處理功能
- 針對 OpenAI API 限制自動對大於 25MB 的檔案進行分割處理

## 安裝步驟

1. 安裝所需依賴項：

```bash
pip install -r requirements.txt
```

2. 設定環境變數：

創建一個名為 `.env` 的文件，並填入以下內容：

```
# OpenAI API密鑰
OPENAI_API_KEY=your_openai_api_key_here

# Hugging Face Token (用於pyannote.audio模型)
HF_TOKEN=your_huggingface_token_here

# Azure OpenAI設定(如果使用Azure OpenAI)
AZURE_OPENAI_API_KEY=your_azure_openai_api_key_here
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint_here
AZURE_OPENAI_DEPLOYMENT=your_azure_openai_deployment_name_here
AZURE_OPENAI_API_VERSION=your_azure_openai_api_version_here
```

請替換以上變數為您的實際值：
- 申請 OpenAI API 密鑰：[https://platform.openai.com/](https://platform.openai.com/)
- 申請 Hugging Face 令牌：[https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
- 您需要在 Hugging Face 上接受 pyannote/speaker-diarization-3.0 模型的使用條款

## 執行應用

```bash
python app.py
```

應用將在 http://localhost:8080 啟動。

## 支援的音訊格式

系統支援以下音訊格式：
- WAV
- MP3
- M4A
- AAC
- FLAC

## 注意事項

- 音訊檔案大小限制為 100MB
- 如果檔案大於 25MB，系統會自動分段處理
- OpenAI API 可能需要付費使用
- pyannote.audio 使用免費的 Hugging Face 模型，但需要接受模型使用條款
- 說話者辨識結果會根據每個語音段落的重疊情況分配最合適的說話者 