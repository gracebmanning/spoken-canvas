#!/usr/bin/env python3
"""
Base class for speech recognizers.
Defines the interface that all speech recognizer implementations must follow.
"""

from abc import ABC, abstractmethod


class SpeechRecognizerBase(ABC):
    """
    Abstract base class for speech recognition engines.
    
    All speech recognizer implementations (Vosk, Whisper, etc.) should inherit
    from this class and implement its abstract methods.
    """
    
    @abstractmethod
    def __init__(self, **kwargs):
        """
        Initialize the speech recognizer.
        
        Args:
            **kwargs: Implementation-specific configuration options
        """
        pass
    
    @abstractmethod
    def start_stream(self, frames_per_buffer=4000):
        """
        Open the audio input stream.
        
        Args:
            frames_per_buffer: Number of frames per buffer
        """
        pass
    
    @abstractmethod
    def process_audio(self):
        """
        Process audio from the stream and return recognized text.
        
        Returns:
            List of recognized words (lowercase), or empty list if no speech detected.
            Should return None if stream is not started.
        """
        pass
    
    @abstractmethod
    def reset(self):
        """
        Reset the recognizer state.
        
        This should clear any recognition history/context.
        """
        pass
    
    @abstractmethod
    def stop_stream(self):
        """Stop and close the audio stream."""
        pass
    
    @abstractmethod
    def cleanup(self):
        """
        Clean up all resources.
        
        This should close streams, release audio devices, etc.
        """
        pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self.cleanup()
