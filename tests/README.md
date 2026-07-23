# Test Scripts

This folder contains example scripts demonstrating the voice-controlled animation system.

## Running a Script

```bash
python listener/listen2.py tests/<path-to-script>
```

This serves the editor at `http://localhost:8100` and hot-reloads on save. Step through with **Ctrl + →** / **Ctrl + ←** (landing on a bracket runs it) and restart with **Ctrl + ↑**. Allow the microphone and click once in the page for audio-reactive scripts to respond.

## Creating Your Own Scripts

Use `[code]` for continuous effects, and `[!code]` for one-shot instructions and fixed tweens.
Target a world explicitly using `browser_2d` or `browser_3d`.
Read `TIME` and `MIC` directly inside continuous brackets.
End with `[RESET()]` to clear.
