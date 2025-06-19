# Meeting Transcriber

An intelligent meeting transcription and analysis system that combines OpenAI's Whisper API for speech-to-text, Pyannote.audio for speaker diarization, and a powerful AI summarization engine.

## ✨ Features

- 🎧 **High-Quality Transcription**: Utilizes OpenAI's `whisper-1` model for accurate audio transcription.
- 👥 **Speaker Diarization**: Employs `pyannote/speaker-diarization-3.1` to distinguish between different speakers in the audio.
- 📝 **AI-Powered Summaries**: Generates comprehensive meeting summaries, including a global overview, and speaker-specific highlights.
- 💻 **Web Interface**: A clean and intuitive web UI built with Flask for easy uploading, monitoring, and management of meeting records.
- ⏱️ **Real-Time Progress**: Track the processing status of your meetings in real-time with Server-Sent Events.
- 💾 **Multiple Export Formats**: Download transcripts as standard `.srt`, speaker-diarization data as `.rttm`, or a combined transcript with speaker labels (`.srt`).
- ▶️ **Audio Playback**: Listen to the processed audio directly in the browser.

## ⚙️ System Requirements

### Supported Audio Formats
- M4A
- MP3
- WAV
- FLAC
- WEBM

### Prerequisites
- **Python 3.8+**
- **FFmpeg**: Must be installed and available in the system's PATH.
- An active **OpenAI API Key** (or Azure OpenAI credentials).
- An active **Hugging Face Token**.

### Limitations
- **Maximum File Size**: 100MB (configurable).
- The application automatically compresses audio to optimize for the Whisper API's 25MB limit.

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/meeting-transcriber.git
cd meeting-transcriber
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Set Up Environment Variables
Create a `.env` file in the project root and add the following variables:

```env
# Flask Secret Key (change this to a random string)
SECRET_KEY='a-very-secret-key'

# Hugging Face Token (for pyannote.audio)
# Get one from https://huggingface.co/settings/tokens
HF_TOKEN='your-hugging-face-token'

# --- Option 1: Standard OpenAI API ---
OPENAI_API_KEY='your-openai-api-key'

# --- Option 2: Azure OpenAI Service ---
# Uncomment and fill these if you are using Azure
# AZURE_OPENAI_ENDPOINT='your-azure-endpoint'
# AZURE_OPENAI_KEY='your-azure-api-key'
# AZURE_OPENAI_API_VERSION='2024-05-01-preview'
# AZURE_OPENAI_MODEL='gpt-4o-mini'
```
**Note**: You must accept the user agreement for the `pyannote/speaker-diarization-3.1` model on Hugging Face to use the diarization feature.

### 4. Initialize the Database
The database will be created and initialized automatically on the first run.

### 5. Run the Application
```bash
python run.py
```
The application will be available at `http://127.0.0.1:8080`.

## 🛠️ How It Works

1.  **Upload**: Upload an audio file through the web interface. You can optionally specify the number of speakers.
2.  **Processing**: A background job starts, and the UI displays the live progress.
    - The audio is converted to a 16kHz mono WAV for diarization and compressed to an Opus `.webm` for transcription.
    - **Transcription**: The compressed audio is sent to the Whisper API.
    - **Diarization**: The WAV audio is processed by `pyannote.audio` to identify speaker segments.
    - **Merging**: The transcript and speaker segments are merged to create a final, speaker-labeled SRT file.
3.  **Review & Download**: Once complete, you can view the meeting details, play back the audio, generate an AI summary, and download the `.srt` and `.rttm` files.

## 💻 Tech Stack

-   **Backend**: Flask (Python)
-   **Frontend**: Vanilla JavaScript, HTML5, CSS3
-   **Database**: SQLite
-   **Audio Processing**: `ffmpeg`, `pydub`
-   **Transcription**: OpenAI Whisper API
-   **Diarization**: `pyannote.audio`
-   **AI Summarization**: OpenAI / Azure OpenAI GPT Models
-   **Dependencies**: `pyannote.audio`, `openai`, `python-dotenv`, `srt`, `flask`, `Flask-Moment`, `pydub`

## 📄 License

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file for details. 