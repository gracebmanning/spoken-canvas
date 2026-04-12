#!/usr/bin/env python3
"""
Whisper-based Speech Recognition Module
Provides real-time speech-to-text using OpenAI Whisper and PyAudio.

Note: Whisper is optimized for file transcription, not streaming.
This implementation buffers audio chunks for periodic transcription.
"""

import re
import io
import sys
import os
import wave
import tempfile
from contextlib import contextmanager
from pathlib import Path
import numpy as np
import whisper
import pyaudio

from .speech_recognizer_base import SpeechRecognizerBase


@contextmanager
def suppress_whisper_output():
    """Context manager to suppress Whisper's verbose output."""
    # Save current stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    
    try:
        # Redirect to devnull
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
        yield
    finally:
        # Restore stdout/stderr
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = old_stdout
        sys.stderr = old_stderr


class WhisperRecognizer(SpeechRecognizerBase):
    """
    Speech recognizer using OpenAI Whisper.
    
    Since Whisper doesn't support true streaming, this implementation:
    - Buffers audio chunks in memory
    - Periodically transcribes accumulated audio
    - Returns new words since last transcription
    """
    
    def __init__(self, model_name="base", sample_rate=16000, buffer_duration=3.0, language="en"):
        """
        Initialize Whisper recognizer.
        
        Args:
            model_name: Whisper model size (tiny, base, small, medium, large)
            sample_rate: Audio sample rate in Hz (default: 16000)
            buffer_duration: How many seconds of audio to buffer before transcribing (default: 3.0)
            language: Language code for recognition (default: "en" for English, None for auto-detect)
        """
        self.model_name = model_name
        self.sample_rate = sample_rate
        self.buffer_duration = buffer_duration
        self.language = language
        
        # Calculate buffer size in frames
        self.buffer_size_frames = int(sample_rate * buffer_duration)
        
        # Initialize Whisper model
        print(f"Loading Whisper model '{model_name}'...")
        with suppress_whisper_output():
            self.model = whisper.load_model(model_name)
        print(f"Whisper model loaded successfully!")
        
        # Audio buffer
        self.audio_buffer = []
        self.total_frames = 0
        
        # Track what we've transcribed
        self.all_recognized_words = []
        
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
            List of recognized words (lowercase), or empty list if no new speech detected.
            Returns None if stream is not started.
        """
        if self.stream is None:
            return None
        
        # Read audio data
        data = self.stream.read(4000, exception_on_overflow=False)
        
        # Add to buffer
        self.audio_buffer.append(data)
        self.total_frames += len(data) // 2  # 2 bytes per int16 sample
        
        # Check if we have enough audio to transcribe
        if self.total_frames >= self.buffer_size_frames:
            words = self._transcribe_buffer()
            return words
        
        return []
    
    def _transcribe_buffer(self):
        """
        Transcribe accumulated audio buffer and return new words.
        
        Returns:
            List of new words recognized since last transcription
        """
        if not self.audio_buffer:
            return []
        
        try:
            # Combine buffer chunks into single audio array
            audio_bytes = b''.join(self.audio_buffer)
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Transcribe with Whisper (suppress all output)
            with suppress_whisper_output():
                result = self.model.transcribe(
                    audio_array,
                    language=self.language,  # Use configured language
                    word_timestamps=False,
                    verbose=False,
                    fp16=False  # Use fp32 for CPU compatibility
                )
            
            # Get full transcribed text
            current_text = result.get('text', '').strip()
            
            # Extract all words from current transcription
            if current_text:
                current_words = re.findall(r'\b\w+\b', current_text.lower())
                
                # Find new words (words that weren't in our previous list)
                previous_count = len(self.all_recognized_words)
                
                # Simple approach: if text is similar to what we had, extract the difference
                # Otherwise, return all words (handles reset/restart scenarios)
                new_words = []
                
                if previous_count > 0 and len(current_words) > previous_count:
                    # Check if current words start with our previous words
                    if current_words[:previous_count] == self.all_recognized_words[-previous_count:]:
                        # Same beginning, get the new words at the end
                        new_words = current_words[previous_count:]
                    else:
                        # Different - might be a restart, return all current words
                        new_words = current_words
                        self.all_recognized_words = []
                elif previous_count == 0:
                    # First transcription
                    new_words = current_words
                
                # Update our running list
                self.all_recognized_words.extend(new_words)
                
                # Clear buffer (fresh start for next chunk)
                self.audio_buffer = []
                self.total_frames = 0
                
                return new_words
            else:
                # No text, clear buffer
                self.audio_buffer = []
                self.total_frames = 0
                return []
        
        except Exception as e:
            print(f"Error transcribing with Whisper: {e}")
            # Clear buffer on error
            self.audio_buffer = []
            self.total_frames = 0
            return []
    
    def reset(self):
        """Reset the recognizer state (clears recognition history)."""
        self.audio_buffer = []
        self.total_frames = 0
        self.all_recognized_words = []
    
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
