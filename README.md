# AI Meeting Transcriber

A system that uses OpenAI Whisper API for meeting audio transcription and analysis, combined with pyannote.audio for speaker diarization.

## Main Features

- 🎙️ **Speech-to-Text**: High-quality audio transcription using OpenAI Whisper API
- 👥 **Speaker Diarization**: Speaker separation and identification using pyannote.audio
- 📝 **Meeting Summary**: Automatic generation of meeting summaries
- ✅ **Speaker Action Items**: Extraction of action items based on each participant's speech content

## System Requirements

### Supported Audio Formats
- WAV
- MP3
- M4A
- AAC
- FLAC

### Limitations
- Audio file size limit: 100MB
- Files larger than 25MB will be automatically segmented
- Valid OpenAI API key required
- Valid Hugging Face token required

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Setup
Create a `.env` file with the following environment variables:

```env
# OpenAI API Settings
OPENAI_API_KEY=your_openai_api_key_here

# Hugging Face Token
HF_TOKEN=your_huggingface_token_here

# Azure OpenAI Settings (Optional)
AZURE_OPENAI_API_KEY=your_azure_openai_api_key_here
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint_here
AZURE_OPENAI_DEPLOYMENT=your_azure_openai_deployment_name_here
AZURE_OPENAI_API_VERSION=your_azure_openai_api_version_here
```

### 3. Launch Application
```bash
python app.py
```
The application will start at http://localhost:8080

## Required Setup

1. **OpenAI API Key**
   - Apply at [OpenAI Platform](https://platform.openai.com/)
   - Note: May require paid usage

2. **Hugging Face Token**
   - Apply at [Hugging Face Settings](https://huggingface.co/settings/tokens)
   - Must accept the terms of use for pyannote/speaker-diarization-3.0 model

## Changelog

### 2023-05-20
- Integrated pyannote.audio for speaker diarization
- Optimized integration of Whisper API transcription with speaker diarization

### 2023-05-19
- Upgraded to OpenAI Whisper API
- Added large audio file segmentation feature
- Implemented automatic file segmentation for files >25MB

## Notes

- The system automatically assigns the most appropriate speaker based on speech segment overlap
- High-quality recording equipment is recommended for optimal recognition results
- Ensure sufficient API quota for processing large meeting recordings

## License

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