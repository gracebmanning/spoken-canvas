"""
Speech Recognizer Package

This package contains different speech recognition implementations.
All recognizers implement the SpeechRecognizerBase interface.

Available recognizers:
- VoskRecognizer: Offline speech recognition using Vosk
- WhisperRecognizer: Speech recognition using OpenAI Whisper
"""

from .speech_recognizer_base import SpeechRecognizerBase
from .vosk_recognizer import VoskRecognizer

# Whisper is optional - only import if available
try:
    from .whisper_recognizer import WhisperRecognizer
    __all__ = ['SpeechRecognizerBase', 'VoskRecognizer', 'WhisperRecognizer']
except ImportError:
    __all__ = ['SpeechRecognizerBase', 'VoskRecognizer']
