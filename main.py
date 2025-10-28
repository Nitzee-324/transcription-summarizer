from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
import json
import numpy as np
import websockets
import os
from dotenv import load_dotenv
from datetime import datetime
import uuid
import aiohttp
import time
from dataclasses import dataclass
from typing import Optional, List, Deque
from collections import deque
import logging
import io
from fastapi.templating import Jinja2Templates
from fastapi import Request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Create necessary directories
os.makedirs("questions", exist_ok=True)
os.makedirs("transcripts", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
os.makedirs("templates", exist_ok=True)

app = FastAPI(title="Interview Bot API")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@dataclass
class AudioBuffer:
    """
    Buffer for audio data to optimize network transmission.
    Helps in batching audio chunks for efficient sending.
    """
    max_size: int = 6
    buffer: Deque[bytes] = None
    
    def __post_init__(self):
        if self.buffer is None:
            self.buffer = deque(maxlen=self.max_size)
    
    def add_chunk(self, audio_data: bytes):
        """Add audio chunk to buffer"""
        self.buffer.append(audio_data)
    
    def get_buffered_data(self) -> bytes:
        """Get all buffered data and clear buffer"""
        if not self.buffer:
            return b''
        combined = b''.join(self.buffer)
        self.buffer.clear()
        return combined
    
    def should_send(self) -> bool:
        """Check if buffer has enough data to send"""
        return len(self.buffer) >= self.max_size
    
    def has_data(self) -> bool:
        """Check if buffer has any data"""
        return len(self.buffer) > 0

@dataclass
class ThrottledChecker:
    """
    Prevents too frequent AI completion checks to avoid rate limiting
    and reduce API costs.
    """
    min_interval: float = 2.0
    last_check: float = 0.0
    
    async def should_check(self) -> bool:
        """Check if enough time has passed since last AI check"""
        now = time.time()
        if now - self.last_check >= self.min_interval:
            self.last_check = now
            return True
        return False

@dataclass
class AdaptiveTimer:
    """
    Adaptive timing system that adjusts delays based on network conditions
    and operation type for optimal performance.
    """
    base_delays = {
        'ai_check': 2.0,
        'silence_detection': 0.3,
        'recovery': 0.5,
        'buffer_flush': 0.05,
        'tts_delay': 1.0
    }
    network_latency: float = 0.1
    
    async def adaptive_sleep(self, operation_type: str):
        """Sleep for adaptive duration based on operation type and network conditions"""
        delay = self.base_delays.get(operation_type, 0.3) + self.network_latency
        await asyncio.sleep(delay)

class ConnectionHealthMonitor:
    """
    Monitors WebSocket connection health and audio transmission status
    to detect and handle connection issues.
    """
    def __init__(self):
        self.last_pong = time.time()
        self.latency_history = deque(maxlen=10)
        self.last_audio_received = time.time()
    
    def update_pong(self):
        """Update last pong time for connection health monitoring"""
        self.last_pong = time.time()
    
    def update_audio_received(self):
        """Update last audio received time for activity monitoring"""
        self.last_audio_received = time.time()
    
    def get_health_score(self) -> float:
        """
        Calculate connection health score based on recent activity.
        Returns score between 0.0 (poor) and 1.0 (excellent)
        """
        time_since_audio = time.time() - self.last_audio_received
        time_since_pong = time.time() - self.last_pong
        
        if time_since_audio > 5.0:
            return 0.0
        elif time_since_audio > 2.0:
            return 0.3
        elif time_since_pong > 10:
            return 0.5
        return 1.0

class TranscriptManager:
    """
    Manages interview transcripts - saving to file and organizing by session.
    """
    def __init__(self, interview_id: str):
        self.interview_id = interview_id
        # Store transcripts in transcripts folder
        self.transcript_filename = f"transcripts/interview_transcript_{self.interview_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.transcripts = []
        
    def add_transcript(self, question: str, answer_segments: list, question_number: int):
        """
        Add a completed question-answer pair to transcripts
        """
        transcript_data = {
            "question_number": question_number,
            "question": question,
            "answer_segments": answer_segments,
            "full_answer": " ".join(answer_segments),
            "timestamp": datetime.now().isoformat(),
            "word_count": sum(len(seg.split()) for seg in answer_segments)
        }
        
        self.transcripts.append(transcript_data)
        self._save_transcript()
        return transcript_data
    
    def _save_transcript(self):
        """Save transcript to JSON file"""
        try:
            data = {
                "interview_id": self.interview_id,
                "created_at": datetime.now().isoformat(),
                "total_questions": len(self.transcripts),
                "transcripts": self.transcripts
            }
            
            with open(self.transcript_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Transcript saved: {self.transcript_filename}")
            
        except Exception as e:
            logger.error(f"Error saving transcript: {e}")

class InterviewSession:
    """
    Represents a single interview session with state management,
    audio processing, and question handling.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.deepgram_ws = None
        self.questions = self._load_questions()
        self.current_question_index = 0
        self.transcript_buffer = []
        self.live_transcript = ""
        self.last_speech_time = time.time()
        self.is_listening = False
        self.is_playing_question = False
        self.current_question = ""
        self.websocket = None  # Store websocket reference
        
        # Smart pause detection settings
        self.silence_threshold = 0.01
        self.initial_pause_duration = 2.0
        self.no_speech_timeout = 8.0
        self.pause_increment = 1.0
        self.max_consecutive_waits = 2
        self.absolute_silence_limit = 15.0
        self.current_pause_duration = self.initial_pause_duration
        self.consecutive_wait_count = 0
        self.answer_start_time = time.time()
        self.has_meaningful_speech = False
        self.last_transcript_length = 0
        self.last_transcript_check_time = time.time()
        
        # Components for latency optimization
        self.audio_buffer = AudioBuffer(max_size=6)
        self.throttled_checker = ThrottledChecker(min_interval=2.5)
        self.adaptive_timer = AdaptiveTimer()
        self.health_monitor = ConnectionHealthMonitor()
        self.groq_api_key = os.getenv('GROQ_API_KEY')
        self.deepgram_api_key = os.getenv('DEEPGRAM_API_KEY')
        
        self.transcript_manager = TranscriptManager(session_id)
        
        self.reset_for_next_question()
    
    def _load_questions(self):
        """
        Load questions from JSON file in questions folder.
        Falls back to default questions if file not found.
        """
        try:
            with open('questions/questions.json', 'r', encoding='utf-8') as f:
                questions = json.load(f)
            logger.info(f"Loaded {len(questions)} questions from file")
            return questions
        except FileNotFoundError:
            logger.warning("Questions file not found, using default questions")
            return [
                "What is the difference between a list and a tuple in Python?",
                "Explain how Python's garbage collection works.",
                "What are decorators in Python and how do you use them?",
                "How does Python handle memory management?",
                "What are Python generators and when would you use them?",
            ]
        except Exception as e:
            logger.error(f"Error loading questions: {e}, using default questions")
            return [
                "What is the difference between a list and a tuple in Python?",
                "Explain how Python's garbage collection works.",
                "What are decorators in Python and how do you use them?",
            ]
    
    async def connect_deepgram(self):
        """
        Establish WebSocket connection to Deepgram for real-time speech recognition
        """
        try:
            api_key = self.deepgram_api_key
            if not api_key:
                raise Exception("DEEPGRAM_API_KEY not found")
            
            # Deepgram connection parameters optimized for interview scenario
            url = (
                f"wss://api.deepgram.com/v1/listen?"
                f"encoding=linear16&"
                f"sample_rate=16000&"
                f"channels=1&"
                f"smart_format=true&"
                f"interim_results=true&"
                f"model=nova-2&"
                f"language=en-US&"
                f"no_delay=true&"
                f"endpointing=100&"
                f"vad_events=true"
            )
            
            headers = {"Authorization": f"Token {api_key}"}
            
            self.deepgram_ws = await websockets.connect(
                url, 
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )
            logger.info("Deepgram connected successfully")
            
            # Test the connection
            await asyncio.sleep(1)
            if self.deepgram_ws.closed:
                logger.error("Deepgram connection closed immediately")
                return False
                
            return True
        except websockets.exceptions.InvalidStatusCode as e:
            if e.status_code == 402:
                logger.error("DEEPGRAM LIMIT REACHED: Payment required - check your usage limits")
            elif e.status_code == 429:
                logger.error("DEEPGRAM RATE LIMIT: Too many requests")
            elif e.status_code == 401:
                logger.error("DEEPGRAM AUTH ERROR: Invalid API key")
            else:
                logger.error(f"Deepgram connection error: {e}")
            return False
        except Exception as e:
            logger.error(f"Deepgram connection error: {e}")
            return False

    async def generate_tts_audio(self, text: str):
        """
        Generate Text-to-Speech audio using Deepgram's TTS API
        Converts question text to speech for playback
        """
        try:
            if not self.deepgram_api_key:
                logger.error("DEEPGRAM_API_KEY not found for TTS")
                return None
            
            url = "https://api.deepgram.com/v1/speak"
            headers = {
                "Authorization": f"Token {self.deepgram_api_key}",
                "Content-Type": "application/json"
            }
            
            # JSON structure for Deepgram TTS
            data = {
                "text": text
            }
            
            logger.info(f"Generating TTS for question: {text[:50]}...")
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        logger.info(f"TTS generated successfully: {len(audio_data)} bytes")
                        return audio_data
                    else:
                        error_text = await response.text()
                        logger.error(f"TTS API error {response.status}: {error_text}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.error("TTS generation timeout")
            return None
        except Exception as e:
            logger.error(f"TTS generation error: {e}")
            return None

    async def start_listening(self):
        """
        Transition from TTS playback to listening mode for user response
        """
        self.is_listening = True
        self.answer_start_time = time.time()
        self.last_speech_time = time.time()
        logger.info("Session now listening for user response")
        
        # Send message to frontend to indicate recording has started
        if self.websocket:
            await self.websocket.send_json({
                "type": "recording_started",
                "message": "Recording started - please speak your answer"
            })
    
    async def check_completion_async(self, question: str, full_answer: str, current_transcript: str):
        """
        Use Groq AI to determine if the user's answer is complete
        or if they're still speaking/thinking
        """
        if not self.groq_api_key:
            return "wait"
        
        prompt = f"""You are analyzing a live Python technical interview. Determine if the candidate's answer is COMPLETE and we should move to next question.

QUESTION: {question}

FULL ANSWER (everything said so far): {full_answer}

CURRENT/LATEST TRANSCRIPT (what they just said): {current_transcript}

DECISION CRITERIA:
- If the FULL ANSWER shows BASIC UNDERSTANDING with at least 1 valid point about the core concept, respond: COMPLETE
- If the FULL ANSWER is factually correct and relevant (even if brief), respond: COMPLETE

- If CURRENT TRANSCRIPT shows the candidate is clearly MID-SENTENCE or says "um", "uh", "and", "so" indicating they want to continue, respond: WAIT
- If CURRENT TRANSCRIPT is empty or very short but FULL ANSWER is substantial and complete, respond: COMPLETE
- If both FULL ANSWER and CURRENT TRANSCRIPT suggest the candidate has finished their thought, respond: COMPLETE
- Only respond WAIT if the candidate is clearly still speaking or the CURRENT TRANSCRIPT indicates they want to add more
- Even if the current_transcript and full_answer is irrelevent to the question, respond : WAIT

CONTEXT ANALYSIS:
- Look at FULL ANSWER to see if the core question has been addressed
- Look at CURRENT TRANSCRIPT to see if they're still actively speaking
- Consider if the answer ends naturally or seems cut off

Respond with ONLY one word: either "COMPLETE" or "WAIT" (no explanation)"""

        max_retries = 2
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                    async with session.post(
                        'https://api.groq.com/openai/v1/chat/completions',
                        headers={
                            'Authorization': f'Bearer {self.groq_api_key}',
                            'Content-Type': 'application/json'
                        },
                        json={
                            'messages': [{'role': 'user', 'content': prompt}],
                            'model': 'llama-3.3-70b-versatile',
                            'max_tokens': 10,
                            'temperature': 0.1,
                            'stream': False
                        }
                    ) as response:
                        
                        if response.status == 429:
                            wait_time = base_delay * (2 ** attempt)
                            logger.warning(f"Rate limited, waiting {wait_time}s")
                            await asyncio.sleep(wait_time)
                            continue
                            
                        if response.status != 200:
                            logger.error(f"Groq API error: {response.status}")
                            return "wait"
                            
                        data = await response.json()
                        
                        if data and 'choices' in data and data['choices']:
                            result = data['choices'][0]['message']['content'].strip().upper()
                            return "complete" if "COMPLETE" in result else "wait"
                        return "wait"
                        
            except asyncio.TimeoutError:
                logger.warning(f"Groq API timeout (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (2 ** attempt))
                continue
            except Exception as e:
                logger.error(f"Groq API error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (2 ** attempt))
                continue
        
        return "wait"
    
    def get_next_question(self):
        """Get the next question from the questions list"""
        if self.current_question_index < len(self.questions):
            question = self.questions[self.current_question_index]
            self.current_question_index += 1
            self.current_question = question
            return question
        return None
    
    def reset_for_next_question(self):
        """Reset state for the next question"""
        self.transcript_buffer = []
        self.live_transcript = ""
        self.last_speech_time = time.time()
        self.current_pause_duration = self.initial_pause_duration
        self.consecutive_wait_count = 0
        self.answer_start_time = time.time()
        self.has_meaningful_speech = False
        self.last_transcript_length = 0
        self.last_transcript_check_time = time.time()
        self.audio_buffer = AudioBuffer(max_size=6)
        self.is_listening = False  # Don't start listening until TTS is done

# Global session storage
sessions = {}

@app.get("/")
async def serve_interview_page(request: Request):
    """Serve the main interview interface"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/session/start")
async def start_session():
    """
    Start a new interview session
    Returns session ID and initial configuration
    """
    session_id = str(uuid.uuid4())[:8]
    session = InterviewSession(session_id)
    sessions[session_id] = session
    
    return {
        "session_id": session_id,
        "total_questions": len(session.questions),
        "transcript_file": session.transcript_manager.transcript_filename,
        "features": ["audio_buffering", "adaptive_timing", "health_monitoring", "tts"]
    }

@app.get("/api/session/{session_id}/question")
async def get_question(session_id: str):
    """Get the next question for a session with TTS audio"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    question = session.get_next_question()
    
    if question:
        session.reset_for_next_question()
        
        # Generate TTS audio for the question
        tts_audio = await session.generate_tts_audio(question)
        
        return {
            "question": question,
            "question_number": session.current_question_index,
            "total_questions": len(session.questions),
            "tts_audio": tts_audio.hex() if tts_audio else None
        }
    else:
        return {
            "question": None,
            "message": "Interview completed"
        }

@app.get("/api/session/{session_id}/question/audio")
async def get_question_audio(session_id: str):
    """Stream TTS audio for the current question"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    if not session.current_question:
        raise HTTPException(status_code=404, detail="No current question")
    
    logger.info(f"Generating TTS audio for question: {session.current_question}")
    tts_audio = await session.generate_tts_audio(session.current_question)
    
    if not tts_audio:
        raise HTTPException(status_code=500, detail="Failed to generate TTS audio")
    
    return StreamingResponse(
        io.BytesIO(tts_audio),
        media_type="audio/wav",
        headers={
            "Content-Length": str(len(tts_audio)),
            "Content-Type": "audio/wav"
        }
    )

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time audio streaming and transcript processing
    Handles bidirectional communication between client and Deepgram
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")
    
    if session_id not in sessions:
        await websocket.send_json({"error": "Session not found"})
        await websocket.close()
        return
    
    session = sessions[session_id]
    session.websocket = websocket  # Store websocket reference
    
    # Connect to Deepgram for speech recognition
    if not await session.connect_deepgram():
        await websocket.send_json({"error": "Failed to connect to Deepgram"})
        await websocket.close()
        return

    # Start background tasks
    auto_check_task = asyncio.create_task(optimized_auto_check_completion(session, websocket))
    health_task = asyncio.create_task(monitor_connection_health(session, websocket))

    async def receive_from_deepgram():
        """
        Receive real-time transcripts from Deepgram WebSocket
        Processes speech recognition results and updates session state
        """
        try:
            logger.info("Starting Deepgram message receiver...")
            while True:
                try:
                    message = await asyncio.wait_for(session.deepgram_ws.recv(), timeout=10.0)
                    session.health_monitor.update_audio_received()
                    data = json.loads(message)
                    
                    logger.info(f"Deepgram message type: {data.get('type')}")
                    
                    if data.get('type') == 'Results':
                        transcript = ""
                        is_final = False
                        
                        if 'channel' in data and 'alternatives' in data['channel']:
                            alternatives = data['channel']['alternatives']
                            if alternatives:
                                transcript = alternatives[0].get('transcript', '').strip()
                                is_final = data.get('is_final', False)
                        
                        logger.info(f"Deepgram transcript: '{transcript}' (is_final: {is_final})")
                        
                        if transcript and session.is_listening:
                            if is_final:
                                session.transcript_buffer.append(transcript)
                                session.live_transcript = ""
                                session.last_speech_time = time.time()
                                
                                if len(transcript.split()) >= 1:
                                    session.has_meaningful_speech = True
                                    logger.info(f"Meaningful speech detected: '{transcript}'")
                            else:
                                session.live_transcript = transcript
                                if len(transcript.split()) >= 1:
                                    session.last_speech_time = time.time()
                                    session.has_meaningful_speech = True
                            
                            # Send transcript update to client
                            await websocket.send_json({
                                "type": "transcript",
                                "transcript": transcript,
                                "is_final": is_final,
                                "full_answer": " ".join(session.transcript_buffer),
                                "live": session.live_transcript
                            })
                    elif data.get('type') == 'error':
                        logger.error(f"Deepgram error: {data}")
                    elif data.get('type') == 'Metadata':
                        # Keep connection alive - no action needed
                        pass
                        
                except asyncio.TimeoutError:
                    # No message from Deepgram, but continue listening
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Deepgram connection closed")
                    break
                    
        except Exception as e:
            logger.error(f"Deepgram receive error: {e}")

    async def send_to_deepgram():
        """
        Send audio data from client to Deepgram for speech recognition
        Handles both audio bytes and control messages
        """
        logger.info("Starting Deepgram audio sender...")
        try:
            while True:
                try:
                    # Wait for audio data from client
                    message = await asyncio.wait_for(websocket.receive(), timeout=1.0)
                    
                    if "bytes" in message:
                        audio_data = message["bytes"]
                        logger.info(f"Received audio data from client: {len(audio_data)} bytes")
                        
                        # Send to Deepgram if we're in listening mode
                        if session.deepgram_ws and not session.deepgram_ws.closed and session.is_listening:
                            try:
                                await session.deepgram_ws.send(audio_data)
                                session.health_monitor.update_audio_received()
                                logger.info(f"Sent {len(audio_data)} bytes to Deepgram")
                            except websockets.exceptions.ConnectionClosed:
                                logger.error("Deepgram connection closed during send")
                                break
                            except Exception as e:
                                logger.error(f"Error sending to Deepgram: {e}")
                                break
                        else:
                            logger.warning(f"Not sending audio to Deepgram - listening: {session.is_listening}, deepgram_ws: {session.deepgram_ws is not None and not session.deepgram_ws.closed}")
                                
                    elif "text" in message:
                        # Handle text control messages from client
                        data = json.loads(message["text"])
                        if data.get("type") == "start_listening":
                            logger.info("Received start_listening message from client")
                            await session.start_listening()
                        elif data.get("type") == "tts_finished":
                            logger.info("Received tts_finished message from client")
                            await session.start_listening()
                            
                except asyncio.TimeoutError:
                    # No data received, but continue listening
                    continue
                except WebSocketDisconnect:
                    logger.info("Client WebSocket disconnected")
                    break
                    
        except Exception as e:
            logger.error(f"Audio streaming error: {e}")

    try:
        # Run both communication tasks concurrently
        await asyncio.gather(
            receive_from_deepgram(),
            send_to_deepgram(),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup tasks and connections
        auto_check_task.cancel()
        health_task.cancel()
        if session.deepgram_ws:
            await session.deepgram_ws.close()
        logger.info(f"WebSocket closed for session {session_id}")

async def optimized_auto_check_completion(session: InterviewSession, websocket: WebSocket):
    """
    Background task that automatically checks answer completion
    Uses smart pause detection and AI analysis to determine when to move to next question
    """
    await asyncio.sleep(2)  # Initial delay to allow recording to start
    
    while True:
        try:
            if not session.is_listening:
                logger.debug("Auto-check: Session not listening, waiting...")
                await asyncio.sleep(0.5)
                continue
            
            # Check connection health before proceeding
            health_score = session.health_monitor.get_health_score()
            if health_score < 0.5:
                logger.warning(f"Poor connection health: {health_score}")
                await asyncio.sleep(1.0)
                continue
            
            current_time = time.time()
            silence_duration = current_time - session.last_speech_time
            total_elapsed = current_time - session.answer_start_time
            
            full_answer = " ".join(session.transcript_buffer)
            current_transcript = session.live_transcript
            current_transcript_length = len(full_answer)
            
            # Check for meaningful speech (at least 1 word)
            total_words = len(full_answer.split())
            has_content = total_words >= 1
            
            # Update meaningful speech flag
            if has_content and not session.has_meaningful_speech:
                session.has_meaningful_speech = True
                logger.info(f"Meaningful speech updated: {total_words} words")
            
            logger.info(f"Auto-check: silence={silence_duration:.1f}s, total={total_elapsed:.1f}s, words={total_words}, listening={session.is_listening}")
            
            # CASE 1: No meaningful speech after timeout
            if not session.has_meaningful_speech:
                if total_elapsed >= session.no_speech_timeout:
                    logger.info(f"No meaningful answer after {session.no_speech_timeout}s (total words: {total_words})")
                    await move_to_next(session, websocket, "no_answer")
                    continue
                await asyncio.sleep(0.5)
                continue
            
            # Check transcript growth to detect if user is still active
            if current_time - session.last_transcript_check_time >= 2.0:
                if current_transcript_length > session.last_transcript_length:
                    logger.info(f"Transcript growing: {session.last_transcript_length} -> {current_transcript_length} chars")
                    session.consecutive_wait_count = 0
                    session.last_transcript_length = current_transcript_length
                session.last_transcript_check_time = current_time
            
            # CASE 2: Absolute silence limit - user has stopped speaking entirely
            if silence_duration >= session.absolute_silence_limit:
                logger.info(f"Absolute silence limit: {session.absolute_silence_limit}s")
                await move_to_next(session, websocket, "forced_complete")
                continue
            
            # CASE 3: Check pause threshold with throttling and AI analysis
            if silence_duration >= session.current_pause_duration:
                if not await session.throttled_checker.should_check():
                    await asyncio.sleep(0.5)
                    continue
                    
                logger.info(f"Pause detected: {silence_duration:.1f}s - Checking with AI (words: {total_words})")
                
                await websocket.send_json({
                    "type": "checking_completion",
                    "message": "AI checking answer",
                    "health_score": health_score
                })
                
                # Use AI to determine if answer is complete
                decision = await session.check_completion_async(
                    session.current_question,
                    full_answer,
                    current_transcript
                )
                
                if decision == "complete":
                    logger.info("AI: Answer COMPLETE")
                    await move_to_next(session, websocket, "complete")
                else:
                    logger.info("AI: WAIT for more")
                    session.consecutive_wait_count += 1
                    
                    if session.consecutive_wait_count >= session.max_consecutive_waits:
                        logger.info(f"Max waits reached: {session.consecutive_wait_count}")
                        await move_to_next(session, websocket, "forced_complete")
                    else:
                        # Increase pause duration for next check
                        session.current_pause_duration = min(
                            session.current_pause_duration + session.pause_increment,
                            6.0
                        )
                        session.last_speech_time = time.time()
                        
                        await websocket.send_json({
                            "type": "wait_continue",
                            "message": "Continue speaking",
                            "consecutive_waits": session.consecutive_wait_count
                        })
            
            await asyncio.sleep(0.3)
            
        except Exception as e:
            logger.error(f"Auto-check error: {e}")
            await asyncio.sleep(1.0)

async def monitor_connection_health(session: InterviewSession, websocket: WebSocket):
    """
    Background task to monitor connection health and adjust parameters
    Sends periodic health updates to the client
    """
    while True:
        try:
            health_score = session.health_monitor.get_health_score()
            
            # Adjust network latency based on health
            if health_score < 0.3:
                session.adaptive_timer.network_latency = 0.5
            elif health_score < 0.7:
                session.adaptive_timer.network_latency = 0.2
            else:
                session.adaptive_timer.network_latency = 0.1
            
            # Send health update to client periodically
            try:
                await websocket.send_json({
                    "type": "health_update",
                    "health_score": health_score,
                    "network_latency": session.adaptive_timer.network_latency
                })
            except Exception as e:
                logger.debug(f"Could not send health update: {e}")
            
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Health monitoring error: {e}")
            await asyncio.sleep(5)

async def move_to_next(session: InterviewSession, websocket: WebSocket, reason: str):
    """
    Handle transition to next question
    Saves current transcript and notifies client
    """
    # Save transcript with answer segments
    session.transcript_manager.add_transcript(
        session.current_question,
        session.transcript_buffer,
        session.current_question_index
    )
    
    session.is_listening = False
    
    await websocket.send_json({
        "type": "move_to_next",
        "reason": reason,
        "message": "Moving to next question"
    })

@app.get("/api/session/{session_id}/transcripts")
async def get_transcripts(session_id: str):
    """Get all transcripts for a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    return {
        "transcripts": session.transcript_manager.transcripts,
        "file": session.transcript_manager.transcript_filename
    }

@app.get("/api/session/{session_id}/health")
async def get_health(session_id: str):
    """Get health status of a session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    return {
        "health_score": session.health_monitor.get_health_score(),
        "network_latency": session.adaptive_timer.network_latency,
        "audio_buffer_size": len(session.audio_buffer.buffer)
    }

@app.get("/api/debug/deepgram-test")
async def deepgram_test():
    """Test Deepgram TTS API connectivity and configuration"""
    import aiohttp
    
    try:
        api_key = os.getenv('DEEPGRAM_API_KEY')
        if not api_key:
            return {"error": "DEEPGRAM_API_KEY not found"}
        
        # Test TTS API with simple text
        async with aiohttp.ClientSession() as session:
            url = "https://api.deepgram.com/v1/speak"
            headers = {
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json"
            }
            
            # Test with different payload formats
            test_payloads = [
                {"text": "Hello, this is a test of the Deepgram TTS system."},
                {"text": "Test message for TTS", "model": "aura-asteria-en"}
            ]
            
            results = []
            for i, payload in enumerate(test_payloads):
                try:
                    async with session.post(url, headers=headers, json=payload) as response:
                        if response.status == 200:
                            audio_data = await response.read()
                            results.append({
                                "payload": i+1,
                                "status": "success", 
                                "audio_size": len(audio_data)
                            })
                        else:
                            error_text = await response.text()
                            results.append({
                                "payload": i+1,
                                "status": "failed",
                                "error": f"Status {response.status}",
                                "details": error_text
                            })
                except Exception as e:
                    results.append({
                        "payload": i+1,
                        "status": "error",
                        "error": str(e)
                    })
            
            return {
                "tts_test_results": results,
                "message": "Check which payload format works with your Deepgram account"
            }
                    
    except Exception as e:
        return {"error": f"Test failed: {str(e)}"}
    
@app.get("/api/debug/connections")
async def debug_connections():
    """Debug endpoint to check all active connections and their states"""
    connection_info = []
    for session_id, session in sessions.items():
        connection_info.append({
            "session_id": session_id,
            "deepgram_connected": session.deepgram_ws is not None and not session.deepgram_ws.closed,
            "is_listening": session.is_listening,
            "health_score": session.health_monitor.get_health_score(),
            "audio_buffer_size": len(session.audio_buffer.buffer),
            "network_latency": session.adaptive_timer.network_latency,
            "transcript_length": len(session.transcript_buffer),
            "current_question": session.current_question
        })
    return {"active_connections": connection_info}

@app.delete("/api/session/{session_id}")
async def end_session(session_id: str):
    """End a specific interview session"""
    if session_id in sessions:
        del sessions[session_id]
        return {"message": "Session ended"}
    raise HTTPException(status_code=404, detail="Session not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")