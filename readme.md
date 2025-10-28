markdown
# Interview Bot

A real-time AI-powered interview bot that conducts technical interviews with speech recognition and text-to-speech capabilities.

## Features

- 🎤 Real-time speech-to-text using Deepgram
- 🔊 Text-to-speech for questions using Deepgram TTS
- 🤖 AI-powered answer analysis using Groq
- 💬 Live transcript display
- 📝 Automatic transcript saving
- 🎯 Smart pause detection and completion checking

## Setup

1. **Clone or download the project files**

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
Set up environment variables
Create a .env file in the root directory:

env
DEEPGRAM_API_KEY=your_deepgram_api_key_here
GROQ_API_KEY=your_groq_api_key_here
Add interview questions
Create questions/questions.json with your questions:

json
[
  "What is the difference between a list and a tuple in Python?",
  "Explain how Python's garbage collection works.",
  "What are decorators in Python and how do you use them?"
]
API Keys
You need to get these API keys:

Deepgram API Key: For speech recognition and TTS

Sign up at deepgram.com

Get your API key from the dashboard

Groq API Key: For AI completion analysis

Sign up at groq.com

Get your API key from the console

Project Structure
text
interview-bot/
├── main.py                 # FastAPI application
├── requirements.txt        # Python dependencies
├── .env                   # Environment variables
├── questions/
│   └── questions.json     # Interview questions
├── transcripts/           # Generated transcripts
├── static/
│   ├── css/
│   │   └── style.css     # Frontend styles
│   └── js/
│       └── app.js        # Frontend JavaScript
└── templates/
    └── index.html        # Main web interface