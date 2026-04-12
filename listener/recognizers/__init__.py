"""
Speech Recognizer Package

This package contains different speech recognition implementations.
All recognizers implement the SpeechRecognizerBase interface.

Available recognizers:
- VoskRecognizer: Offline speech recognition using Vosk
- (Future) WhisperRecognizer: Speech recognition using OpenAI Whisper
"""

from .speech_recognizer_base import SpeechRecognizerBase
from .vosk_recognizer import VoskRecognizer

__all__ = ['SpeechRecognizerBase', 'VoskRecognizer']
