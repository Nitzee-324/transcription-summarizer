/**
 * Mock Interview Bot - Frontend Application
 * Handles WebSocket communication, audio recording, and UI updates
 * for the AI-powered mock interview system.
 */

// Configuration
const API_URL = 'http://localhost:8000';

// Global state variables
let sessionId = null;
let ws = null;
let audioContext = null;
let currentQuestion = null;
let totalQuestions = 0;
let currentQuestionNum = 0;
let audioProcessor = null;
let sourceNode = null;
let transcriptFile = null;
let audioStreamer = null;
let connectionHealth = 100;
let latencyHistory = [];
let isPlayingQuestion = false;
let isRecording = false;

// DOM Elements cache
const elements = {
    // Buttons and controls
    startBtn: document.getElementById('startBtn'),
    restartBtn: document.getElementById('restartBtn'),
    
    // Status indicators
    statusDot: document.getElementById('statusDot'),
    statusText: document.getElementById('statusText'),
    healthFill: document.getElementById('healthFill'),
    healthText: document.getElementById('healthText'),
    connectionStatus: document.getElementById('connectionStatus'),
    latencyInfo: document.getElementById('latencyInfo'),
    
    // Content sections
    startSection: document.getElementById('startSection'),
    questionSection: document.getElementById('questionSection'),
    completionSection: document.getElementById('completionSection'),
    
    // Question and transcript display
    questionText: document.getElementById('questionText'),
    liveTranscript: document.getElementById('liveTranscript'),
    fullTranscript: document.getElementById('fullTranscript'),
    wordCount: document.getElementById('wordCount'),
    statusMessage: document.getElementById('statusMessage'),
    progressText: document.getElementById('progressText'),
    progressFill: document.getElementById('progressFill'),
    transcriptFile: document.getElementById('transcriptFile'),
    
    // Status messages
    aiStatus: document.getElementById('aiStatus'),
    ttsStatus: document.getElementById('ttsStatus'),
    ttsError: document.getElementById('ttsError'),
    recordingStatus: document.getElementById('recordingStatus')
};

/**
 * AudioStreamer - Handles audio data buffering and transmission
 * Optimizes network usage by batching audio chunks
 */
class AudioStreamer {
    constructor() {
        this.buffer = [];
        this.bufferSize = 4; // Number of chunks to batch together
        this.isSending = false;
        this.sampleRate = 16000;
        this.chunkDuration = 100; // ms
        this.totalBytesSent = 0;
        this.sendCount = 0;
        this.chunkCount = 0;
    }

    /**
     * Add audio data to buffer and trigger send if buffer is full
     * @param {Float32Array} inputData - Raw audio data from microphone
     */
    addAudioData(inputData) {
        this.chunkCount++;
        
        // Convert float32 to int16 for Deepgram compatibility
        const int16Data = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
            int16Data[i] = Math.max(-32768, Math.min(32767, inputData[i] * 32768));
        }
        
        this.buffer.push(int16Data.buffer);
        
        // Send buffer if it reaches the size threshold and not already sending
        if (!this.isSending && this.buffer.length >= this.bufferSize) {
            this.sendBuffer();
        }
    }

    /**
     * Send buffered audio data to WebSocket
     * Implements retry logic and error handling
     */
    async sendBuffer() {
        if (this.isSending || this.buffer.length === 0) return;
        
        this.isSending = true;
        this.sendCount++;
        
        try {
            // Only send if WebSocket is connected and recording is active
            if (ws && ws.readyState === WebSocket.OPEN && isRecording) {
                const combinedBuffer = await this.combineAudioChunks(this.buffer);
                this.totalBytesSent += combinedBuffer.byteLength;
                
                // Send the combined audio buffer
                ws.send(combinedBuffer);
                this.buffer = [];
                
                console.log(`Sent audio buffer ${this.sendCount}: ${combinedBuffer.byteLength} bytes`);
            } else {
                // Clear buffer if not ready to send
                this.buffer = [];
            }
        } catch (error) {
            console.error('Error sending audio buffer:', error);
        } finally {
            this.isSending = false;
            
            // If more data accumulated while sending, schedule next send
            if (this.buffer.length > 0) {
                setTimeout(() => this.sendBuffer(), 10);
            }
        }
    }

    /**
     * Combine multiple audio chunks into a single buffer
     * @param {Array} chunks - Array of ArrayBuffer audio chunks
     * @returns {ArrayBuffer} Combined audio buffer
     */
    async combineAudioChunks(chunks) {
        const totalLength = chunks.reduce((acc, chunk) => acc + chunk.byteLength, 0);
        const result = new Uint8Array(totalLength);
        let offset = 0;
        
        for (const chunk of chunks) {
            result.set(new Uint8Array(chunk), offset);
            offset += chunk.byteLength;
        }
        
        return result.buffer;
    }

    /**
     * Force send any remaining audio data in buffer
     */
    flush() {
        if (this.buffer.length > 0) {
            this.sendBuffer();
        }
    }
}

/**
 * Initialize application event listeners
 */
function initializeEventListeners() {
    elements.startBtn.addEventListener('click', startInterview);
    if (elements.restartBtn) {
        elements.restartBtn.addEventListener('click', restartInterview);
    }
    
    // Handle page visibility changes to manage recording
    document.addEventListener('visibilitychange', handleVisibilityChange);
}

/**
 * Handle page visibility changes to pause/resume recording
 */
function handleVisibilityChange() {
    if (document.hidden && isRecording) {
        console.log('Page hidden, consider pausing recording');
    } else if (isRecording) {
        console.log('Page visible, recording active');
    }
}

/**
 * Start a new interview session
 * Initializes WebSocket connection and loads first question
 */
async function startInterview() {
    try {
        console.log('Starting new interview session...');
        
        // Create new session via API
        const response = await fetch(`${API_URL}/api/session/start`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to start session: ${response.status}`);
        }
        
        const data = await response.json();
        sessionId = data.session_id;
        totalQuestions = data.total_questions;
        transcriptFile = data.transcript_file;
        
        console.log(`Session started: ${sessionId}, ${totalQuestions} questions`);
        
        // Initialize audio streamer for efficient audio transmission
        audioStreamer = new AudioStreamer();
        
        // Connect to WebSocket for real-time communication
        connectWebSocket();
        
        // Update UI to show question section
        showSection('questionSection');
        
        updateStatus('Connecting...', 'warning');
        updateConnectionStatus('Connecting to interview session...');
        
    } catch (error) {
        console.error('Failed to start interview:', error);
        alert('Failed to start interview: ' + error.message);
    }
}

/**
 * Restart interview - reset state and start over
 */
function restartInterview() {
    // Reset all state variables
    sessionId = null;
    currentQuestion = null;
    totalQuestions = 0;
    currentQuestionNum = 0;
    connectionHealth = 100;
    isPlayingQuestion = false;
    isRecording = false;
    
    // Close existing connections
    if (ws) {
        ws.close();
    }
    stopRecording();
    
    // Reset UI
    showSection('startSection');
    updateStatus('Ready', 'ready');
    updateConnectionStatus('Ready to start new interview');
    updateConnectionHealth(100);
    
    console.log('Interview reset, ready to start new session');
}

/**
 * Establish WebSocket connection for real-time audio and data transfer
 */
function connectWebSocket() {
    console.log(`Connecting to WebSocket for session: ${sessionId}`);
    
    ws = new WebSocket(`${API_URL.replace('http', 'ws')}/ws/${sessionId}`);
    
    ws.onopen = async () => {
        console.log('WebSocket connected successfully');
        updateStatus('Connected', 'active');
        updateConnectionHealth(100);
        updateConnectionStatus('Connected - Starting interview...');
        
        // Load the first question
        await loadNextQuestion();
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            console.log('WebSocket message received:', data);
            handleWebSocketMessage(data);
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateStatus('Connection Error', 'error');
        updateConnectionHealth(0);
        updateConnectionStatus('Connection error - Please try again');
    };
    
    ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        updateStatus('Disconnected', 'error');
        updateConnectionStatus('Connection closed');
    };
}

/**
 * Handle incoming WebSocket messages from the server
 * @param {Object} data - Parsed WebSocket message data
 */
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'transcript':
            handleTranscriptUpdate(data);
            break;
            
        case 'recording_started':
            handleRecordingStarted();
            break;
            
        case 'checking_completion':
            handleAIChecking(data);
            break;
            
        case 'wait_continue':
            handleWaitContinue(data);
            break;
            
        case 'move_to_next':
            handleMoveToNext(data);
            break;
            
        case 'health_update':
            handleHealthUpdate(data);
            break;
            
        default:
            console.log('Unknown message type:', data.type);
    }
}

/**
 * Handle transcript updates from Deepgram
 * @param {Object} data - Transcript data with live and final transcripts
 */
function handleTranscriptUpdate(data) {
    if (data.is_final) {
        // Final transcript - add to full answer
        elements.fullTranscript.textContent = data.full_answer || 'Speak naturally to answer the question';
        elements.liveTranscript.textContent = 'Processing...';
    } else {
        // Interim transcript - show live feedback
        elements.liveTranscript.textContent = data.live || 'Listening...';
    }
    
    // Update word count
    const wordCount = data.full_answer ? data.full_answer.split(' ').filter(w => w).length : 0;
    elements.wordCount.textContent = `Words: ${wordCount}`;
}

/**
 * Handle recording started notification
 */
function handleRecordingStarted() {
    elements.recordingStatus.classList.add('show');
    elements.liveTranscript.textContent = 'Recording active - Speak your answer';
    updateConnectionStatus('Recording - Speak your answer');
}

/**
 * Handle AI completion check notification
 * @param {Object} data - Health score and status data
 */
function handleAIChecking(data) {
    elements.aiStatus.classList.add('show');
    elements.statusMessage.textContent = 'AI checking answer completeness...';
    
    if (data.health_score !== undefined) {
        updateConnectionHealth(data.health_score * 100);
    }
}

/**
 * Handle wait/continue instruction from AI
 * @param {Object} data - Wait count and message
 */
function handleWaitContinue(data) {
    elements.aiStatus.classList.remove('show');
    elements.statusMessage.textContent = `Continue speaking... (${data.consecutive_waits || 0}/2)`;
}

/**
 * Handle move to next question instruction
 * @param {Object} data - Reason and message for moving to next question
 */
function handleMoveToNext(data) {
    elements.aiStatus.classList.remove('show');
    elements.recordingStatus.classList.remove('show');
    transitionToNextQuestion(data.reason);
}

/**
 * Handle health update from server
 * @param {Object} data - Health score and network latency
 */
function handleHealthUpdate(data) {
    updateConnectionHealth(data.health_score * 100);
    updateLatencyInfo(data.network_latency);
}

/**
 * Load the next question from the server
 * Includes TTS audio generation and playback
 */
async function loadNextQuestion() {
    try {
        console.log('Loading next question...');
        
        const response = await fetch(`${API_URL}/api/session/${sessionId}/question`);
        
        if (!response.ok) {
            throw new Error(`Failed to load question: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.question) {
            // Update question data
            currentQuestion = data.question;
            currentQuestionNum = data.question_number;
            totalQuestions = data.total_questions;
            
            // Update UI with new question
            elements.questionText.textContent = data.question;
            elements.progressText.textContent = `Question ${currentQuestionNum} / ${totalQuestions}`;
            elements.progressFill.style.width = `${(currentQuestionNum / totalQuestions) * 100}%`;
            
            // Reset transcript display
            elements.fullTranscript.textContent = 'Speak naturally to answer the question';
            elements.liveTranscript.textContent = 'Playing question audio...';
            elements.wordCount.textContent = 'Words: 0';
            elements.statusMessage.textContent = '';
            
            console.log(`Loaded question ${currentQuestionNum}: ${currentQuestion.substring(0, 50)}...`);
            
            // Play TTS audio for the question
            await playQuestionAudio();
            
        } else {
            // No more questions - interview completed
            showCompletion();
        }
    } catch (error) {
        console.error('Failed to load question:', error);
        alert('Failed to load question: ' + error.message);
    }
}

/**
 * Play TTS audio for the current question
 * Handles audio playback and transitions to recording mode
 */
async function playQuestionAudio() {
    try {
        // Show TTS status and prepare UI
        elements.ttsStatus.classList.add('show');
        elements.ttsError.classList.remove('show');
        elements.recordingStatus.classList.remove('show');
        elements.liveTranscript.textContent = 'Playing question audio...';
        updateConnectionStatus('Playing question audio...');
        
        isPlayingQuestion = true;
        
        // Fetch TTS audio from server
        const response = await fetch(`${API_URL}/api/session/${sessionId}/question/audio`);
        
        if (!response.ok) {
            throw new Error(`Failed to get TTS audio: ${response.status}`);
        }
        
        const audioBlob = await response.blob();
        
        if (audioBlob.size === 0) {
            throw new Error('Empty audio blob received');
        }
        
        const audioUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(audioUrl);
        
        // Set up audio event handlers
        audio.onended = async () => {
            console.log('TTS audio playback completed');
            await handleTTSCompleted();
        };
        
        audio.onerror = (error) => {
            console.error('Audio playback error:', error);
            handleTTSError('Audio playback failed');
        };
        
        // Start audio playback
        await audio.play().catch(error => {
            console.error('Audio play failed:', error);
            handleTTSError('Audio play failed');
        });
        
    } catch (error) {
        console.error('TTS playback error:', error);
        handleTTSError('Failed to play question audio');
    }
}

/**
 * Handle TTS audio completion - transition to recording mode
 */
async function handleTTSCompleted() {
    isPlayingQuestion = false;
    elements.ttsStatus.classList.remove('show');
    elements.recordingStatus.classList.add('show');
    elements.liveTranscript.textContent = 'Recording started - Speak your answer now';
    updateConnectionStatus('Recording - Speak your answer');
    
    // Notify server that TTS finished and we're ready to record
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: "tts_finished"
        }));
    }
    
    // Start audio recording
    await startRecording();
}

/**
 * Handle TTS playback errors - fallback to manual reading
 * @param {string} errorMessage - Error description for user display
 */
function handleTTSError(errorMessage) {
    isPlayingQuestion = false;
    elements.ttsStatus.classList.remove('show');
    elements.ttsError.classList.add('show');
    elements.liveTranscript.textContent = 'Audio error - Please read the question and start speaking';
    console.error('TTS Error:', errorMessage);
    
    // Start recording anyway as fallback
    startRecording();
}

/**
 * Start audio recording from user's microphone
 * Sets up audio processing and WebSocket transmission
 */
async function startRecording() {
    try {
        isRecording = true;
        
        console.log('Starting audio recording...');
        
        // Request microphone access with optimal settings for speech recognition
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                latency: 0.01
            } 
        });
        
        // Set up audio context for processing
        audioContext = new AudioContext({ 
            sampleRate: 16000,
            latencyHint: 'interactive'
        });
        
        // Create audio source from microphone
        sourceNode = audioContext.createMediaStreamSource(stream);
        
        // Set up audio processor for real-time processing
        audioProcessor = audioContext.createScriptProcessor(1024, 1, 1);
        
        // Process audio data in real-time
        audioProcessor.onaudioprocess = (e) => {
            if (audioStreamer && ws && ws.readyState === WebSocket.OPEN && isRecording && !isPlayingQuestion) {
                const inputData = e.inputBuffer.getChannelData(0);
                audioStreamer.addAudioData(inputData);
            }
        };
        
        // Connect audio nodes
        sourceNode.connect(audioProcessor);
        audioProcessor.connect(audioContext.destination);
        
        updateStatus('Recording', 'active');
        elements.liveTranscript.textContent = 'Recording active - Speak your answer';
        updateConnectionStatus('Recording - Speak your answer');
        
        console.log('Audio recording started successfully');
        
    } catch (error) {
        console.error('Error starting recording:', error);
        
        // Fallback: try without advanced settings
        try {
            await startFallbackRecording();
        } catch (fallbackError) {
            console.error('Fallback recording also failed:', fallbackError);
            alert('Microphone access required for the interview. Please allow microphone permissions and try again.');
        }
    }
}

/**
 * Fallback recording method with basic settings
 * Used when advanced audio constraints are not supported
 */
async function startFallbackRecording() {
    isRecording = true;
    
    console.log('Starting fallback recording...');
    
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = new AudioContext();
    sourceNode = audioContext.createMediaStreamSource(stream);
    audioProcessor = audioContext.createScriptProcessor(1024, 1, 1);
    
    audioProcessor.onaudioprocess = (e) => {
        if (audioStreamer && ws && ws.readyState === WebSocket.OPEN && isRecording && !isPlayingQuestion) {
            const inputData = e.inputBuffer.getChannelData(0);
            audioStreamer.addAudioData(inputData);
        }
    };
    
    sourceNode.connect(audioProcessor);
    audioProcessor.connect(audioContext.destination);
    
    updateStatus('Recording', 'active');
    updateConnectionStatus('Recording - Speak your answer');
    
    console.log('Fallback recording started');
}

/**
 * Stop audio recording and clean up resources
 */
async function stopRecording() {
    isRecording = false;
    console.log('Stopping audio recording...');
    
    // Flush any remaining audio data
    if (audioStreamer) {
        audioStreamer.flush();
    }
    
    // Disconnect and clean up audio nodes
    if (audioProcessor) {
        audioProcessor.disconnect();
        audioProcessor = null;
    }
    
    if (sourceNode) {
        sourceNode.disconnect();
        sourceNode = null;
    }
    
    if (audioContext) {
        await audioContext.close();
        audioContext = null;
    }
    
    console.log('Audio recording stopped');
}

/**
 * Transition to next question after completion
 * @param {string} reason - Reason for moving to next question
 */
async function transitionToNextQuestion(reason) {
    console.log(`Moving to next question. Reason: ${reason}`);
    
    elements.statusMessage.textContent = 'Moving to next question...';
    
    // Stop current recording
    await stopRecording();
    
    // Brief pause before loading next question
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Load next question
    await loadNextQuestion();
}

/**
 * Show interview completion screen
 */
async function showCompletion() {
    console.log('Interview completed');
    
    await stopRecording();
    
    // Update UI to show completion section
    showSection('completionSection');
    updateStatus('Completed', 'active');
    updateConnectionHealth(100);
    updateConnectionStatus('Interview completed successfully');
    
    // Show transcript file location
    if (transcriptFile) {
        elements.transcriptFile.textContent = `Transcript saved to: ${transcriptFile}`;
    }
    
    // Close WebSocket connection
    if (ws) {
        ws.close();
    }
}

/**
 * Show specific section and hide others
 * @param {string} sectionId - ID of the section to show
 */
function showSection(sectionId) {
    // Hide all sections
    elements.startSection.classList.remove('active');
    elements.questionSection.classList.remove('active');
    elements.completionSection.classList.remove('active');
    
    // Show requested section
    elements[sectionId].classList.add('active');
}

/**
 * Update connection status display
 * @param {string} status - Status text to display
 * @param {string} type - Status type: 'ready', 'active', 'warning', 'error'
 */
function updateStatus(status, type = 'ready') {
    elements.statusText.textContent = status;
    
    // Reset status dot classes
    elements.statusDot.className = 'status-dot';
    
    // Add appropriate class based on type
    switch (type) {
        case 'active':
            elements.statusDot.classList.add('active');
            break;
        case 'warning':
            elements.statusDot.classList.add('warning');
            break;
        case 'error':
            elements.statusDot.classList.add('error');
            break;
        default:
            // 'ready' - no additional class
            break;
    }
}

/**
 * Update connection status message with styling
 * @param {string} message - Status message to display
 */
function updateConnectionStatus(message) {
    elements.connectionStatus.textContent = message;
    
    // Update styling based on message content
    const statusEl = elements.connectionStatus;
    statusEl.style.background = '#d1ecf1';
    statusEl.style.borderColor = '#bee5eb';
    statusEl.style.color = '#0c5460';
    
    if (message.includes('error') || message.includes('Error')) {
        statusEl.style.background = '#f8d7da';
        statusEl.style.borderColor = '#f5c6cb';
        statusEl.style.color = '#721c24';
    } else if (message.includes('Completed')) {
        statusEl.style.background = '#d1edf7';
        statusEl.style.borderColor = '#bee5eb';
        statusEl.style.color = '#0c5460';
    } else if (message.includes('Recording')) {
        statusEl.style.background = '#d1f7e6';
        statusEl.style.borderColor = '#bee5c4';
        statusEl.style.color = '#0c5460';
    } else if (message.includes('Playing')) {
        statusEl.style.background = '#f0e6ff';
        statusEl.style.borderColor = '#d9c9ff';
        statusEl.style.color = '#4b0082';
    }
}

/**
 * Update connection health indicator
 * @param {number} score - Health score (0-100)
 */
function updateConnectionHealth(score) {
    connectionHealth = score;
    elements.healthFill.style.width = `${score}%`;
    elements.healthText.textContent = `${Math.round(score)}%`;
    
    // Update color based on health score
    elements.healthFill.className = 'health-fill';
    if (score < 30) {
        elements.healthFill.classList.add('error');
    } else if (score < 70) {
        elements.healthFill.classList.add('warning');
    }
}

/**
 * Update latency information display
 * @param {number} latency - Latency in seconds
 */
function updateLatencyInfo(latency) {
    const latencyMs = Math.round(latency * 1000);
    elements.latencyInfo.textContent = `Latency: ${latencyMs}ms`;
}

/**
 * Initialize the application when DOM is loaded
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Mock Interview Bot initialized');
    initializeEventListeners();
    
    // Start periodic health checks if session exists
    setInterval(async () => {
        if (sessionId) {
            try {
                const response = await fetch(`${API_URL}/api/session/${sessionId}/health`);
                if (response.ok) {
                    const health = await response.json();
                    updateConnectionHealth(health.health_score * 100);
                    updateLatencyInfo(health.network_latency);
                }
            } catch (error) {
                // Silent fail for health checks - don't show errors to user
                console.debug('Health check failed:', error);
            }
        }
    }, 10000); // Check every 10 seconds
});

// Export for testing purposes (if needed)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        AudioStreamer,
        updateStatus,
        updateConnectionHealth
    };
}