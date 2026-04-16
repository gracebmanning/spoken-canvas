# Test Scripts

This folder contains example scripts demonstrating the voice-controlled animation system.

## Available Scripts

### `basic_browser_test.script`
A simple test script that creates a red circle.

**Usage:**
```bash
python listener/listen.py tests/basic_browser_test.script
```

**Script text:** "Let's begin with a circle"

**What it does:**
- Tests basic speech recognition
- Tests command execution
- Creates a single red circle when you reach the end

---

### `system_architecture.script`
An interactive explanation of the system architecture using animated diagrams.

**Usage:**
```bash
python listener/listen.py tests/system_architecture.script
```

**What it demonstrates:**
- System architecture with three components (Listener, Server, Interpreter)
- Communication flow between components
- Available drawing commands (boxes, arrows, text)
- The modular design of the system
- Uses the new `box()`, `arrow()`, and `text()` functions

**Tip:** This script is longer and demonstrates the full capabilities of the system. It creates an animated presentation showing how the components work together.

---

## Running the Scripts

1. **Start the server:**
   ```bash
   python listener/serve.py
   ```

2. **Open the browser interpreter:**
   - Open `interpreters/browser/paper_and_anime_playground.html` in your browser
   - Or add it as a Browser Source in OBS

3. **Run the listener with a script:**
   ```bash
   # With Vosk (fast)
   python listener/listen.py tests/basic_browser_test.script
   
   # With Whisper (better accuracy)
   python listener/listen.py tests/system_architecture.script --recognizer whisper
   ```

4. **Read the script aloud** and watch the graphics appear!

## Controls

While the listener is running:
- **R** - Reset (clears recognition state and graphics)
- **Q** - Quit

## Creating Your Own Scripts

Script format:
```
Narration text that you speak. [command()]

More narration. [another_command()]

Create variables: [let myCircle = circle(50, "blue")]

Use them later: [move(myCircle, 400, 300, 2)]

Reset everything: [RESET()]
```

See the main README for available drawing commands.
