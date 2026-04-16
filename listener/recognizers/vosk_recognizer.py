#!/usr/bin/env python3
"""
Vosk-based Speech Recognition Module
Provides real-time speech-to-text using Vosk and PyAudio.
"""

import json
import re
from pathlib import Path
import vosk
import pyaudio

from .speech_recognizer_base import SpeechRecognizerBase


class VoskRecognizer(SpeechRecognizerBase):
    """
    Speech recognizer using Vosk.
    
    This class encapsulates all Vosk-specific functionality for speech recognition.
    It can be replaced with alternative implementations (e.g., Whisper) without
    changing the main listener logic.
    """
    
    def __init__(self, model_path=None, sample_rate=16000):
        """
        Initialize Vosk recognizer.
        
        Args:
            model_path: Path to Vosk model directory (optional - auto-detects if None)
            sample_rate: Audio sample rate in Hz (default: 16000)
        """
        # Auto-detect model path if not provided
        if model_path is None:
            model_path = str(Path(__file__).parent / "models" / "vosk")
        
        self.model_path = model_path
        self.sample_rate = sample_rate
        
        # Initialize Vosk
        print(f"Loading Vosk model from {model_path}...")
        self.model = vosk.Model(model_path)
        self.recognizer = vosk.KaldiRecognizer(self.model, sample_rate)
        self.recognizer.SetWords(True)
        
        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        self.stream = None
    
    def start_stream(self, frames_per_buffer=4000):
        """
        Open audio input stream.
        
        Args:
            frames_per_buffer: Number of frames per buffer
        """
        if self.stream is not None:
            raise RuntimeError("Stream already started")
        
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=frames_per_buffer
        )
    
    def process_audio(self):
        """
        Process audio from the stream and return recognized text.
        
        Returns:
            List of recognized words (lowercase), or empty list if no speech detected.
            Returns None if stream is not started.
        """
        if self.stream is None:
            return None
        
        # Read audio data
        data = self.stream.read(4000, exception_on_overflow=False)
        
        # Process with Vosk
        if self.recognizer.AcceptWaveform(data):
            result = json.loads(self.recognizer.Result())
            text = result.get('text', '')
            
            if text:
                # Extract words
                words = re.findall(r'\b\w+\b', text.lower())
                return words
        
        return []
    
    def reset(self):
        """Reset the recognizer state (clears recognition history)."""
        self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
        self.recognizer.SetWords(True)
    
    def stop_stream(self):
        """Stop and close the audio stream."""
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
    
    def cleanup(self):
        """Clean up resources."""
        self.stop_stream()
        self.audio.terminate()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()
