# Real-Time Voice-Controlled Animation System

A modular system for creating live animations controlled by voice, perfect for live coding performances, educational demonstrations, and interactive presentations.

## Architecture

The system consists of three main components:

### 1. **Listener** (`listener/listen.py`)

- Captures speech using microphone
- Recognizes speech with Vosk (fast) or Whisper (accurate)
- Tracks current position in script
- Extracts and sends commands to the server
- Displays script progress in real-time window

### 2. **Server** (`listener/serve.py`)

- FastAPI WebSocket server
- Acts as central communication hub
- Broadcasts commands to all connected interpreters
- Manages multiple client connections

### 3. **Interpreter** (`interpreters/browser/`)

- Receives commands via WebSocket
- Executes drawing/animation commands
- Uses Paper.js for vector graphics
- Uses Anime.js for smooth animations
- Can run in browser or OBS

**Flow:** Speech → Listener → Server → Interpreter(s) → Graphics

See `tests/system_architecture.script` for an animated explanation of the architecture.

## Quick Start

### 1. Install Dependencies

```bash
# Core dependencies
pip install fastapi uvicorn websocket-client pygame

# For Vosk (recommended - low latency)
pip install vosk pyaudio

# For Whisper (optional - better accuracy)
pip install openai-whisper numpy
```

You will also need the NDI Runtime and NDI OBS Plugin installed on your device:

- [NDI Runtime](https://ndi.video/tools/)
- [DistroAV (formerly OBS-NDI)](https://obsproject.com/forum/resources/distroav-network-audio-video-in-obs-studio-using-ndi%C2%AE-technology.528/)

### 2. Start the Server

```bash
python listener/serve.py
```

Server runs at `http://localhost:8000`

### 3. Open the Browser Interpreter

Open `interpreters/browser/paper_and_anime_playground.html` in your browser, or add as a Browser Source in OBS:

- URL: `http://127.0.0.1:8000` (or open the HTML file directly)
- Width: 1920
- Height: 1080

### 4. Start the Listener

```bash
# Using Vosk (fast, low latency)
python listener/listen.py tests/basic_browser_test.script

# Using Whisper (better accuracy)
python listener/listen.py tests/basic_browser_test.script --recognizer whisper
```

### 5. Speak the Script

Read the script aloud: **"Let's begin with a circle"**

A red circle should appear when you reach the end!

## Available Drawing Commands

The browser interpreter supports these functions:

### Basic Shapes

- `circle(radius, color, x, y)` - Create a circle
- `square(size, color, x, y)` - Create a square
- `rect(width, height, color, x, y)` - Create a rectangle
- `ellipse(width, height, color, x, y)` - Create an ellipse
- `box(width, height, color, x, y, borderWidth)` - Create a bordered box (no fill)

### Annotations

- `text(content, x, y, size, color)` - Create text
- `arrow(fromX, fromY, toX, toY, color, thickness)` - Create an arrow

### Animations

- `move(object, x, y, duration)` - Move object to position
- `scale(object, factor, duration)` - Scale object
- `rotate(object, degrees, duration)` - Rotate object
- `fade(object, opacity, duration)` - Fade object

### Utilities

- `clear()` - Clear all graphics
- `remove(object)` - Remove specific object

### Colors

Supports named colors: `red`, `blue`, `green`, `yellow`, `cyan`, `magenta`, `white`, `black`, `orange`, `purple`, `pink`, `brown`

Or hex codes: `#FF0000`, `#00FF00`, etc.

## Script File Format

Scripts mix narration with embedded commands:

```
This is narration that you speak. [circle(50, "red")]

More narration. [move(c1, 400, 300, 2)]

You can reference variables. [let c2 = circle(30, "blue")]

Reset clears everything. [RESET()]
```

- Text between `[]` is executed as JavaScript
- `let variable =` creates reusable objects
- `RESET()` is a special meta-command that clears state

## Speech Recognizers

### Vosk (Default)

- **Latency:** ~100ms (great for real-time)
- **Accuracy:** Good
- **Size:** ~40MB
- **Best for:** Live performances, interactive demos

### Whisper

- **Latency:** ~3 seconds (buffered chunks)
- **Accuracy:** Excellent
- **Size:** 140MB - 2.9GB
- **Best for:** High-quality transcription, recorded videos

Switch with `--recognizer whisper`

## Project Structure

```
td-websocket-animation/
├── listener/
│   ├── listen.py              # Speech recognition listener
│   ├── serve.py               # WebSocket server
│   ├── requirements.txt       # Python dependencies
│   └── recognizers/           # Speech recognizer modules
│       ├── vosk_recognizer.py
│       ├── whisper_recognizer.py
│       └── models/vosk/       # Vosk model files
├── interpreters/
│   ├── browser/
│   │   └── paper_and_anime_playground.html
│   └── td/                    # TouchDesigner interpreter
└── tests/
    ├── basic_browser_test.script
    └── system_architecture.script
```

## Examples

See the `tests/` directory for example scripts:

- `basic_browser_test.script` - Simple circle creation
- `system_architecture.script` - Animated architecture diagram

## Extending the System

### Add a New Interpreter

1. Connect to WebSocket at `ws://localhost:8000/ws`
2. Listen for `execute` commands with `code` field
3. Execute the code in your environment
4. Listen for `update_position` to track script progress

### Add a New Speech Recognizer

1. Inherit from `SpeechRecognizerBase` in `listener/recognizers/`
2. Implement required methods: `start_stream()`, `process_audio()`, `reset()`, `cleanup()`
3. Add to `recognizers/__init__.py`
4. Update CLI in `listen.py`

See `listener/recognizers/README.md` for details.

## Troubleshooting

### "WebSocket error: Handshake status 404"

- Make sure `serve.py` is running (not SimpleHTTPServer)
- Server should show "BROWSER INTERPRETER SERVER" banner

### "Model not found" (Vosk)

- Vosk model should be at `listener/recognizers/models/vosk/`
- Download from: https://alphacephei.com/vosk/models

### Microphone not working

- Check audio permissions
- Ensure PyAudio is installed correctly
- On Windows, may need to install PortAudio

### Commands not executing

- Check browser console for errors
- Verify WebSocket connection (green "Connected" in top-right)
- Make sure you're speaking the script text accurately

## License

[Add license information]

## Credits

- Paper.js for vector graphics
- Anime.js for animations
- Vosk for offline speech recognition
- OpenAI Whisper for high-quality transcription
