import os
from dotenv import load_dotenv

load_dotenv()

# Deepgram Configuration
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

# LLM Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Audio Configuration
SAMPLE_RATE = 16000
CHUNK_DURATION = 5
CHANNELS = 1

# Summary Configuration
SUMMARIZE_INTERVAL = 30
MIN_WORDS_FOR_SUMMARY = 30
MIN_SEGMENTS_FOR_SUMMARY = 1

# Choose your LLM provider ('gemini' or 'openai')
LLM_PROVIDER = 'gemini'