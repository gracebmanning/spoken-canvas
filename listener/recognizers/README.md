# Speech Recognizer Architecture

## Overview
The speech recognition functionality has been modularized to support multiple recognition engines (Vosk, Whisper, etc.) with a common interface.

## Structure

```
listener/
├── listen.py                          # Main listener script
├── serve.py                           # WebSocket server
└── recognizers/                       # Speech recognizer package
    ├── __init__.py                   # Package exports
    ├── speech_recognizer_base.py     # Abstract base class
    └── vosk_recognizer.py            # Vosk implementation
```

## Components

### `speech_recognizer_base.py`
Abstract base class defining the interface all recognizers must implement:
- `start_stream()` - Open audio input stream
- `process_audio()` - Process audio and return recognized words
- `reset()` - Clear recognition state
- `stop_stream()` - Close audio stream
- `cleanup()` - Release all resources

### `vosk_recognizer.py`
Vosk-based speech recognition implementation:
- Uses Vosk for offline speech-to-text
- Uses PyAudio for audio capture
- Implements the SpeechRecognizerBase interface
- Fully isolated from main listener logic

### `listen.py`
Main listener that:
- Uses any recognizer implementing SpeechRecognizerBase
- Tracks position in script
- Executes commands at specified points
- Forwards commands to interpreters via WebSocket

## Adding a New Recognizer (e.g., Whisper)

To add a new recognizer like Whisper:

1. Create `recognizers/whisper_recognizer.py`:
```python
from .speech_recognizer_base import SpeechRecognizerBase

class WhisperRecognizer(SpeechRecognizerBase):
    def __init__(self, model_name="base", **kwargs):
        # Initialize Whisper
        pass
    
    def start_stream(self, frames_per_buffer=4000):
        # Open audio stream
        pass
    
    def process_audio(self):
        # Process with Whisper, return list of words
        pass
    
    def reset(self):
        # Reset recognition state
        pass
    
    def stop_stream(self):
        # Close stream
        pass
    
    def cleanup(self):
        # Cleanup resources
        pass
```

2. Export it in `recognizers/__init__.py`:
```python
from .whisper_recognizer import WhisperRecognizer
__all__ = ['SpeechRecognizerBase', 'VoskRecognizer', 'WhisperRecognizer']
```

3. Use it in `listen.py`:
```python
from recognizers import WhisperRecognizer  # or VoskRecognizer

# Then in RealtimeListener.__init__:
self.recognizer = WhisperRecognizer(model_name="base")
```

## Usage

### Using Vosk (default):
```bash
# Simple - model is auto-detected
python listener/listen.py tests/basic_browser_test.script

# Explicit recognizer selection
python listener/listen.py tests/basic_browser_test.script --recognizer vosk

# Custom model path (advanced)
python listener/listen.py tests/basic_browser_test.script --recognizer vosk --model /path/to/custom/vosk/model
```

### Using Whisper (when implemented):
```bash
# Default Whisper model (base)
python listener/listen.py tests/basic_browser_test.script --recognizer whisper

# Specify Whisper model size
python listener/listen.py tests/basic_browser_test.script --recognizer whisper --model tiny
python listener/listen.py tests/basic_browser_test.script --recognizer whisper --model small
python listener/listen.py tests/basic_browser_test.script --recognizer whisper --model medium
```

The Vosk model is automatically located at `listener/recognizers/models/vosk/` - no configuration needed!

The script will gracefully handle missing dependencies and provide helpful error messages if a recognizer is not available.
