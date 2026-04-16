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
    ├── vosk_recognizer.py            # Vosk implementation
    ├── whisper_recognizer.py         # Whisper implementation
    └── models/                        # Model files
        └── vosk/                     # Vosk model (auto-detected)
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
- True streaming recognition (low latency)
- Implements the SpeechRecognizerBase interface
- Fully isolated from main listener logic

### `whisper_recognizer.py`
OpenAI Whisper-based speech recognition implementation:
- Uses Whisper for high-quality speech-to-text
- Uses PyAudio for audio capture
- Implements buffering for pseudo-streaming (processes 3-second chunks by default)
- Suppresses verbose Whisper output for clean console
- Defaults to English language recognition for better reliability
- Implements the SpeechRecognizerBase interface
- Note: Higher latency than Vosk (~3 seconds) due to buffering, but better accuracy

### `listen.py`
Main listener that:
- Uses any recognizer implementing SpeechRecognizerBase
- Tracks position in script
- Executes commands at specified points
- Forwards commands to interpreters via WebSocket

## Installation

### For Vosk (default):
```bash
pip install vosk pyaudio
```

### For Whisper:
```bash
pip install openai-whisper numpy pyaudio
# Also requires ffmpeg (system-level install)
```

## Usage

### Using Vosk (default - recommended for low latency):
```bash
# Simple - model is auto-detected
python listener/listen.py tests/basic_browser_test.script

# Explicit recognizer selection
python listener/listen.py tests/basic_browser_test.script --recognizer vosk

# Custom model path (advanced)
python listener/listen.py tests/basic_browser_test.script --recognizer vosk --model /path/to/custom/vosk/model
```

### Using Whisper (better accuracy, higher latency):
```bash
# Default Whisper model (base)
python listener/listen.py tests/basic_browser_test.script --recognizer whisper

# Specify Whisper model size
python listener/listen.py tests/basic_browser_test.script --recognizer whisper --model tiny    # Fastest
python listener/listen.py tests/basic_browser_test.script --recognizer whisper --model small
python listener/listen.py tests/basic_browser_test.script --recognizer whisper --model medium  # Better quality
python listener/listen.py tests/basic_browser_test.script --recognizer whisper --model large   # Best quality
```

## Performance Comparison

| Feature | Vosk | Whisper |
|---------|------|---------|
| Latency | Low (~100ms) | Higher (~3 seconds) |
| Accuracy | Good | Excellent |
| Model Size | ~40MB | 140MB - 2.9GB |
| CPU Usage | Low | Higher |
| Output | Clean, quiet | Clean (suppressed) |
| Language Detection | Manual config | Auto or forced (English default) |
| Best For | Real-time interaction | High-quality transcription |

The Vosk model is automatically located at `listener/recognizers/models/vosk/` - no configuration needed!

The script will gracefully handle missing dependencies and provide helpful error messages if a recognizer is not available.

## Adding More Recognizers

To add additional recognizers (e.g., Google Speech, Azure Speech):

1. Create a new file inheriting from `SpeechRecognizerBase`
2. Implement all required methods
3. Add to `recognizers/__init__.py` exports
4. Update the CLI choices in `listen.py`

Example template:

```python
# recognizers/my_recognizer.py
from .speech_recognizer_base import SpeechRecognizerBase

class MyRecognizer(SpeechRecognizerBase):
    def __init__(self, model_name="default", **kwargs):
        # Initialize your recognizer
        pass
    
    def start_stream(self, frames_per_buffer=4000):
        # Open audio stream
        pass
    
    def process_audio(self):
        # Process audio, return list of words
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
