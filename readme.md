# 🎤 Interview Bot - Real-Time AI Mock Interview System

A **production-grade, full-stack mock interview platform** that conducts technical interviews using real-time speech recognition, natural language processing, and AI-powered answer analysis. Perfect for interview prep, candidate screening, or teaching technical communications.

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green)](https://fastapi.tiangolo.com/)
[![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-orange)](https://en.wikipedia.org/wiki/WebSocket)

---

## 📋 Table of Contents

- [Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [API Documentation](#-api-documentation)
- [Project Structure](#-project-structure)
- [Advanced Features](#-advanced-features)
- [Troubleshooting](#-troubleshooting)

---

## ✨ Key Features

### Real-Time Speech Processing
- 🎤 **Live Speech-to-Text**: Deepgram ASR converts spoken answers to text in real-time
- 🔊 **Text-to-Speech**: Questions are automatically read aloud using Deepgram TTS
- 📊 **Interim + Final Transcripts**: Both live and confirmed transcripts displayed simultaneously

### Intelligent Analysis
- 🤖 **AI Answer Evaluation**: Groq API analyzes answer completeness and quality
- 🎯 **Smart Completion Detection**: Automatically detects when a candidate has finished answering
- ⏱️ **Adaptive Timing**: System adjusts delays based on network conditions and operation type
- 📈 **Connection Health Monitoring**: Real-time latency tracking and connection quality scoring

### Data Management
- 💾 **Persistent Transcripts**: All Q&A sessions automatically saved to JSON with timestamps
- 🆔 **Session Tracking**: Unique interview IDs for easy result organization
- 📝 **Word Count Analytics**: Tracks response length and completeness metrics

### Network Optimization
- 📦 **Smart Audio Buffering**: Batches audio chunks to reduce network overhead
- 🚀 **Rate Limiting Protection**: Throttled AI checks prevent API rate limiting
- 🔄 **WebSocket Communication**: Efficient bidirectional real-time communication
- 💪 **Adaptive Delays**: Dynamically adjusts operation timing for optimal performance

### Professional UI/UX
- 🎨 **Modern Web Interface**: Beautiful gradient design with responsive layout
- 📊 **Real-Time Metrics**: Progress bars, connection health, word counts
- 🔴 **Status Indicators**: Clear visual feedback for recording, TTS, and AI analysis states
- 💬 **Live Transcript Display**: See interim and final transcripts as they appear

---

## 🏗️ System Architecture

### Three-Tier Architecture

```
┌─────────────────────────────────────────────────────┐
│         Frontend (Browser)                          │
│   - Web UI (HTML/CSS/JavaScript)                   │
│   - Audio capture from microphone                  │
│   - Real-time transcript display                   │
└──────────────┬──────────────────────────────────────┘
               │ WebSocket (bi-directional)
               │
┌──────────────▼──────────────────────────────────────┐
│         Backend (FastAPI Server)                    │
│   - WebSocket connection handler                   │
│   - Audio buffer management                        │
│   - Connection health monitoring                   │
│   - API orchestration                              │
└──────────────┬──────────────────────────────────────┘
               │ REST/gRPC APIs
               │
┌──────────────▼──────────────────────────────────────┐
│       External AI Services                          │
│   - Deepgram (Speech Recognition & TTS)            │
│   - Groq (Answer Analysis & Evaluation)            │
└─────────────────────────────────────────────────────┘
```

### Core Components

| Component | Purpose | Technology |
|-----------|---------|-----------|
| **main.py** | FastAPI server, WebSocket handler | FastAPI, Websockets, Aiohttp |
| **interview.py** | CLI interview runner | Python, Groq API, Rich |
| **app.js** | Frontend logic & UI updates | JavaScript Web Audio API |
| **index.html** | Interview UI | HTML5 |
| **style.css** | Responsive styling | CSS3 |

### Data Flow Sequence

```
User clicks "Start" 
    ↓
Backend loads questions
    ↓
TTS reads first question (Deepgram)
    ↓
Frontend captures audio, converts to int16
    ↓
Audio streamed to Deepgram (batched)
    ↓
Transcripts updated in real-time
    ↓
AI analyzes completeness (Groq)
    ↓
Move to next question or prompt for more
    ↓
Session saved to JSON transcript
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Modern web browser (Chrome, Firefox, Safari, Edge)
- Microphone and speaker

### Installation

1. **Clone/Download the project**
   ```bash
   cd transcription-summarizer
   ```

2. **Create virtual environment** (recommended)
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   # Create .env file in project root
   DEEPGRAM_API_KEY=your_deepgram_key_here
   GROQ_API_KEY=your_groq_key_here
   ```

5. **Configure interview questions**
   
   Edit `questions/questions.json`:
   ```json
   [
     "What is the difference between a list and a tuple in Python?",
     "Explain how Python's garbage collection works.",
     "What are decorators in Python and how do you use them?",
     "How does Python handle memory management?",
     "Describe the GIL (Global Interpreter Lock) and its implications."
   ]
   ```

6. **Run the server**
   ```bash
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

7. **Open in browser**
   ```
   http://localhost:8000
   ```

### Running the CLI Version

For a terminal-based interview experience:
```bash
python interview.py
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Deepgram API - Speech Recognition & TTS
DEEPGRAM_API_KEY=gsk_your_key_here

# Groq API - AI Answer Analysis  
GROQ_API_KEY=gsk_your_key_here

# Optional: LLM Provider Selection (config/settings.py)
LLM_PROVIDER=groq  # or 'gemini', 'openai'
```

### API Keys Setup

#### Deepgram (Speech Recognition + TTS)
1. Visit [deepgram.com](https://deepgram.com)
2. Sign up for free account
3. Go to Console → API Keys
4. Copy your API key to `.env`

#### Groq (Answer Analysis)
1. Visit [console.groq.com](https://console.groq.com)
2. Create account
3. Navigate to API Keys
4. Copy your API key to `.env`

### Audio Configuration

Edit `config/settings.py` to customize:

```python
SAMPLE_RATE = 16000          # Audio sample rate (Hz)
CHUNK_DURATION = 5           # Chunk duration (seconds)
CHANNELS = 1                 # Mono audio
SUMMARIZE_INTERVAL = 30      # How often to analyze answers (seconds)
MIN_WORDS_FOR_SUMMARY = 30   # Minimum words before analysis
```

---

## 📖 Usage

### Web Interface

1. **Start Interview**: Click the "Start Interview" button
2. **Listen**: Question audio plays automatically
3. **Speak**: Answer clearly into your microphone
4. **Watch**: Transcript updates in real-time
5. **Next**: System automatically moves to next question when done

### Features While Interviewing

- **Live Transcript**: See interim results as you speak
- **Word Count**: Monitor response length
- **Status Indicator**: See recording, TTS, and AI analysis status
- **Connection Health**: Real-time connection quality indicator
- **Progress Bar**: Track interview progress

### CLI Usage

```bash
python interview.py
```

Then follow the prompts to start the interview. Transcripts are saved automatically.

---

## 🔌 API Documentation

### WebSocket Endpoints

#### Main Interview WebSocket
```
ws://localhost:8000/ws/{session_id}
```

**Server → Client Messages:**
```json
{
  "type": "question",
  "question": "What is a decorator in Python?",
  "question_number": 1,
  "total_questions": 5
}

{
  "type": "transcript",
  "interim": "The decorator is a function that",
  "final": "The decorator is a function that modifies another function"
}

{
  "type": "status",
  "status": "analyzing",
  "connection_health": 95.5
}
```

**Client → Server Messages:**
```json
{
  "type": "audio",
  "data": "base64_encoded_audio_chunk",
  "timestamp": 1234567890
}

{
  "type": "ping"
}
```

### REST Endpoints

#### Get Interview Status
```http
GET /api/interview/{session_id}
```

#### Save Transcript
```http
POST /api/interview/{session_id}/save
```

#### Get Questions
```http
GET /api/questions
```

---

## 📁 Project Structure

```
transcription-summarizer/
├── main.py                          # FastAPI server & WebSocket handler
├── interview.py                     # CLI interview runner
├── requirements.txt                 # Python dependencies
├── .env                            # Environment variables (create this)
├── .gitignore                      # Git ignore rules
│
├── config/
│   ├── settings.py                 # Configuration & constants
│   └── __pycache__/
│
├── questions/
│   └── questions.json              # Interview questions database
│
├── transcripts/                    # Auto-generated interview transcripts
│   ├── interview_transcript_*.json
│   └── ...
│
├── static/
│   ├── css/
│   │   └── style.css              # Frontend styling (520+ lines)
│   └── js/
│       └── app.js                 # Frontend logic (845+ lines)
│
├── templates/
│   └── index.html                 # Web UI template
│
└── readme.md                       # This file
```

---

## 🎯 Advanced Features

### Connection Health Monitoring

The system continuously monitors WebSocket health with:
- **Latency Tracking**: Measures round-trip time for ping/pong
- **Health Score**: 0-100 scale based on connection stability
- **Automatic Recovery**: Attempts reconnection on failure
- **Adaptive Delays**: Adjusts timings based on detected latency

### Intelligent Audio Buffering

```python
AudioBuffer:
  - max_size: 6 chunks
  - Automatically flushes when full
  - Reduces network overhead by ~80%
```

### Throttled AI Analysis

```python
ThrottledChecker:
  - min_interval: 2.0 seconds
  - Prevents API rate limiting
  - Reduces costs while maintaining responsiveness
```

### Adaptive Timing System

Different operations have optimized delays:

| Operation | Base Delay | Adaptive |
|-----------|-----------|----------|
| AI Check | 2.0s | + network latency |
| Silence Detection | 0.3s | + network latency |
| Buffer Flush | 0.05s | + network latency |
| TTS Delay | 1.0s | + network latency |
| Recovery | 0.5s | + network latency |

---

## 🐛 Troubleshooting

### Common Issues

#### "Connection refused" or "Failed to connect"
- Verify FastAPI server is running (`python -m uvicorn main:app --reload`)
- Check if port 8000 is available
- Ensure firewall allows localhost connections

#### No audio output from questions
- Check browser audio settings allow website audio
- Verify Deepgram API key is valid
- Check browser console for errors (F12 → Console)
- Try different browser

#### Transcript not appearing
- Ensure microphone permissions are granted
- Check browser microphone access (Settings → Privacy)
- Test microphone in system settings first
- Check WebSocket connection status in browser DevTools

#### API key errors
- Verify `.env` file exists in project root
- Check API keys are correctly formatted
- Ensure no extra spaces in `.env` file
- Restart server after updating `.env`

#### "Questions not loading"
- Verify `questions/questions.json` exists
- Ensure JSON is valid (check syntax)
- Check file has at least one question

### Debug Mode

Enable verbose logging in `main.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

Check browser console (F12) for frontend errors.

---

## 📊 Output Files

Interview sessions generate transcript files with this structure:

```json
{
  "interview_id": "a1b2c3d4",
  "created_at": "2024-01-15T10:30:45.123456",
  "total_questions": 5,
  "transcripts": [
    {
      "question_number": 1,
      "question": "What is a decorator?",
      "answer_segments": ["A decorator is", "a function that"],
      "full_answer": "A decorator is a function that...",
      "timestamp": "2024-01-15T10:31:00.000000",
      "word_count": 42
    }
  ]
}
```

---

## 🛠️ Technology Stack

### Backend
- **FastAPI** - Modern, fast web framework
- **Websockets** - Real-time bidirectional communication
- **Aiohttp** - Async HTTP client for API calls
- **Python 3.8+** - Core language

### Frontend
- **HTML5** - Semantic markup
- **CSS3** - Modern styling with gradients & animations
- **JavaScript (ES6+)** - Web Audio API for microphone access
- **WebSocket API** - Browser native WebSocket support

### External Services
- **Deepgram** - Speech-to-text & text-to-speech
- **Groq** - Fast LLM for answer analysis
- **Optional**: Gemini or OpenAI for analysis

---

## 📝 License

This project is open source. Feel free to use, modify, and distribute.

---

## 💡 Future Enhancements

- [ ] Multi-language support (interview in any language)
- [ ] Feedback generation (AI provides constructive feedback)
- [ ] Performance analytics dashboard
- [ ] Interview templates & difficulty levels
- [ ] Candidate comparison reports
- [ ] Mobile app version
- [ ] Custom CSS themes
- [ ] Database integration for result history
- [ ] Export to PDF/Word
- [ ] Real-time scoring

---


