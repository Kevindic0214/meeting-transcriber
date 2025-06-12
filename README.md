# 會議轉錄助手

一個結合OpenAI Whisper API的語音轉文字功能與pyannote.audio的語者分離技術的會議記錄和分析系統。

## 主要功能

- 🎙️ **語音轉文字**：使用OpenAI Whisper API進行高品質音訊轉錄
- 👥 **語者分離**：使用pyannote.audio進行語者辨識與分離
- 📝 **會議記錄**：自動產生帶有語者標記的詳細會議記錄
- 📊 **網頁介面**：簡潔直觀的Flask網頁界面，方便上傳和管理會議記錄

## 系統需求

### 支援的音訊格式
- WAV
- MP3
- M4A
- AAC
- FLAC
- WEBM

### 限制條件
- 音訊檔案大小限制：500MB
- 檔案會根據長度自動調整壓縮率以優化處理效能
- 需要有效的OpenAI API金鑰
- 需要有效的Hugging Face令牌

## 快速開始

### 1. 安裝依賴
```bash
pip install -r requirements.txt
```

### 2. 環境設置
創建一個`.env`檔案，包含以下環境變數：

```env
# OpenAI API設置
OPENAI_API_KEY=你的openai_api金鑰

# Hugging Face令牌
HF_TOKEN=你的huggingface令牌

# Flask設置
SECRET_KEY=你的flask密鑰
```

### 3. 啟動應用
```bash
python app.py
```
應用將啟動於 http://localhost:5000

## 功能說明

1. **上傳音訊**：支援多種音訊格式，系統會自動進行預處理和壓縮
2. **自動轉錄**：使用OpenAI Whisper進行高精度語音轉文字
3. **語者辨識**：使用pyannote.audio自動分辨不同發言者
4. **會議記錄**：生成帶有時間戳和語者標記的完整會議記錄
5. **記錄管理**：網頁界面可查看、搜索和下載所有會議記錄

## 必要設置

1. **OpenAI API金鑰**
   - 申請地址：[OpenAI Platform](https://platform.openai.com/)
   - 注意：可能需要付費使用

2. **Hugging Face令牌**
   - 申請地址：[Hugging Face設置](https://huggingface.co/settings/tokens)
   - 必須接受pyannote/speaker-diarization模型的使用條款

## 技術架構

- **後端**：Flask (Python)
- **前端**：Bootstrap + jQuery
- **資料庫**：SQLite
- **音訊處理**：FFMPEG
- **語音辨識**：OpenAI Whisper API
- **語者分離**：pyannote.audio 3.1

## 使用提示

- 系統會根據語音片段重疊度自動分配最合適的發言者
- 建議使用高品質的錄音設備以獲得最佳辨識結果
- 確保API配額足夠處理大型會議錄音
- 對於長時間會議，系統會自動調整壓縮比率以優化處理效能

## 許可證

Copyright 2025 AI Meeting Transcriber

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License. 