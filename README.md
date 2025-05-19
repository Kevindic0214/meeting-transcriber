# 會議錄音轉錄系統

這是一個使用 OpenAI Whisper API 進行會議錄音轉錄和分析的系統，結合了 pyannote.audio 進行說話者辨識。

## 主要功能

- 🎙️ **語音轉文字**：使用 OpenAI Whisper API 進行高品質的語音轉錄
- 👥 **說話者辨識**：使用 pyannote.audio 進行說話者分離和標識
- 📝 **會議摘要**：自動生成會議的摘要
- ✅ **發言者待辦事項**：根據每位參與者的發言內容提取待辦事項

## 系統需求

### 支援的音訊格式
- WAV
- MP3
- M4A
- AAC
- FLAC

### 限制條件
- 音訊檔案大小限制：100MB
- 大於 25MB 的檔案會自動分段處理
- 需要有效的 OpenAI API 密鑰
- 需要有效的 Hugging Face 令牌

## 快速開始

### 1. 安裝依賴
```bash
pip install -r requirements.txt
```

### 2. 環境設定
創建 `.env` 文件並設定以下環境變數：

```env
# OpenAI API設定
OPENAI_API_KEY=your_openai_api_key_here

# Hugging Face Token
HF_TOKEN=your_huggingface_token_here

# Azure OpenAI設定（選用）
AZURE_OPENAI_API_KEY=your_azure_openai_api_key_here
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint_here
AZURE_OPENAI_DEPLOYMENT=your_azure_openai_deployment_name_here
AZURE_OPENAI_API_VERSION=your_azure_openai_api_version_here
```

### 3. 啟動應用
```bash
python app.py
```
應用將在 http://localhost:8080 啟動

## 必要設定

1. **OpenAI API 密鑰**
   - 前往 [OpenAI Platform](https://platform.openai.com/) 申請
   - 注意：可能需要付費使用

2. **Hugging Face 令牌**
   - 前往 [Hugging Face Settings](https://huggingface.co/settings/tokens) 申請
   - 需要接受 pyannote/speaker-diarization-3.0 模型的使用條款

## 更新日誌

### 2023-05-20
- 整合 pyannote.audio 進行說話者辨識
- 優化 Whisper API 轉錄結果與說話者辨識的整合

### 2023-05-19
- 升級至 OpenAI Whisper API
- 新增大型音訊檔案分段處理功能
- 實作自動檔案分割處理機制（>25MB）

## 注意事項

- 系統會根據語音段落的重疊情況自動分配最合適的說話者
- 建議使用高品質的錄音設備以獲得最佳辨識效果
- 請確保有足夠的 API 配額以處理大型會議錄音 