# Real-Time Voice-Controlled Animation System

A real-time, script-driven animation system for live coding performances, educational demos, and interactive presentations. You write a script that mixes narration with bracketed commands; stepping through the script fires those commands at browser-based 2D (Paper.js) and 3D (Three.js) renderers.

## Architecture

The system is centralized around a single editor that acts as the brain, driving two renderers.

### Editor: `listener/listen2/editor.html` (served by `listener/listen2.py`)

The hub. It owns:

- the master clock (`TIME`) and the microphone (`MIC`),
- the FRP engine (`interpreters/browser/frp.js`) and the verb APIs (`api_2d.js`, `api_3d.js`),
- the per-world state store (plain `{id, kind, props}` objects), and
- word stepping — landing on a bracketed command executes it.
  Every frame it evaluates the armed commands, advances tweens and dynamic properties, and posts each world's full current state down to the renderers as an `applyOps` message.

### Renderers: `interpreters/browser/browser_2d.html` & `browser_3d.html`

Dumb output surfaces, embedded in the editor as layered iframes (2D over 3D). They hold no clock, mic, or engine of their own — they receive `applyOps` via `postMessage` and reconstitute native Paper.js / Three.js objects. Nothing renders unless the editor is driving them.

**Flow:** script → editor (FRP engine, per tick) → `applyOps` → renderers → graphics

## Quick Start

No dependencies to install. `listen2.py` is Python standard library. You do need internet access, since the renderers load Paper.js, Three.js, and CodeMirror from CDNs.

```bash
python listener/listen2.py tests/stephen/demo.script
```

This serves the editor at `http://localhost:8100`, auto-opens it in your browser, and hot-reloads whenever you save the `.script` file. Allow microphone access when prompted, and click once anywhere in the page so the browser lets the audio context start.

Flags: `--no-browser` (don't auto-open), `--port N` (default `8100`).

### Controls

Word stepping happens in the editor with **Ctrl** + arrows (so unmodified arrows still edit text normally):

- **Ctrl + →** — step to the next word (landing on a command runs it)
- **Ctrl + ←** — step back
- **Ctrl + ↑** — restart: reset the clock, wipe per-world state and user variables, and reload the renderers
  The editor also has a collapsible **Docs** sidebar (the live command reference, also at `http://localhost:8100/api-docs.html`).

### Streaming to OBS

Both renderers draw into the editor's 1920×1080 output pane; capture that region in OBS. The renderers only produce output while the editor is driving them, so point OBS at the editor rather than at the renderer files directly.

## The Scripting Model

A script is narration with embedded `[ ... ]` commands. The text between brackets is JavaScript, evaluated against the editor's scope.

### Brackets: continuous vs. one-shot

- **`[code]`** — **continuous**. Re-runs every frame from the moment you land on it until the next restart. Use it for ongoing effects: spins, reactive scaling, anything that reads `TIME` or `MIC`.
- **`[!code]`** — **one-shot**. Runs once. Use it for discrete actions and fixed-target tweens: creating shapes, snapping or tweening to a fixed value, colors, fades, removals, and helper/variable definitions.
- **`[RESET()]`** — clears both worlds (sugar for `browser_2d.clear(); browser_3d.clear()`).
  A continuous bracket is _sticky_: once armed it keeps re-asserting every frame and is not superseded by a later command on the same property — only a restart clears it. So a property you intend to tween to a fixed value later should be driven by a one-shot, and an ongoing effect that you want to vary should read a mutable `let` variable you flip with one-shots.

### Worlds

Every verb is reached through an explicit world prefix — there is no bare/global verb:

- **`browser_2d.`** — Paper.js 2D vector graphics (default center `960, 540`)
- **`browser_3d.`** — Three.js 3D scene (default center at the origin)

### Ambient signals

These live objects are always in scope and are mutated in place each frame — read them directly inside continuous brackets:

- `TIME.t` — seconds since start · `TIME.dt` — seconds since last frame
- `MIC.audio_level` — smoothed 0–1 volume · `MIC.pitch` — Hz, or `-1` when silent
- `SCRIPT.words_completed()` — spoken words passed so far

### Variables, helpers, and dynamic values

- `let name = ...` binds a variable that **persists across brackets** (until restart). Define reusable arrow-function helpers this way, e.g. `[!let spin = (s) => browser_3d.rotate(s, 0, TIME.t * s, 0)]`.
- `approach(target, rate = 0.1)` — an exponential smoothing filter for chasing a live signal; only smooths inside a continuous bracket.
- Pass `() => value` where a value must keep updating through a mechanism a plain number can't reach (e.g. a Paper.js circle's radius, which can't be resized after creation). Most of the time, a plain expression inside a continuous bracket is enough, since the whole bracket re-runs.

### Example

```
Let's begin with a shape. [!let c = browser_2d.circle(50, "red")]

Watch it drift. [!browser_2d.move(c, 400, 540, 1.5)]

A cube joins in, spinning as I speak. [!let b = browser_3d.cube(1, 1, 1, "gray")] [browser_3d.rotate(b, TIME.t * 15, TIME.t * 20, 0)]

And it breathes with my voice. [browser_3d.scale(b, 0.9 + MIC.audio_level * 0.4)]

Clean slate. [RESET()]
```

## Command Reference

The authoritative, always-current list of verbs and signatures is the **Docs sidebar in the editor** (`listener/listen2/api-docs.html`, served at `/api-docs.html`). At a glance:

- **`browser_2d`** — `circle`, `square`, `rect`, `ellipse`, `box`, `line`, `arrow`, `text`, `move`, `rotate`, `scale`, `fade`, `remove`, `clear`
- **`browser_3d`** — `cube`, `sphere`, `torus`, `tube`, `cloud`, `move`, `rotate`, `scale`, `noise`, `color`, `opacity`, `remove`, `clear`

### Colors

Verbs accept a hex string (`"#FF8800"`) or any of these named colors (case-insensitive), defined in `interpreters/browser/colors.js`:

`red`, `orange`, `amber`, `yellow`, `lime`, `green`, `emerald`, `teal`, `cyan`, `blue`, `indigo`, `violet`, `purple`, `magenta`, `pink`, `mauve`, `white`, `gray`, `black`, `brown`

## Speech Recognition

Voice-driven word advancement is the project's goal, but the current editor is **keyboard-driven** (Ctrl + arrows). The speech modules — Vosk (low latency) and Whisper (higher accuracy) under `listener/recognizers/`, plus the original `listener/listen.py` listener and `listener/serve.py` WebSocket relay — are retained but **not yet wired into the editor flow**. Wiring them back in is on the roadmap.

## Project Structure

```
spoken-canvas/
├── listener/
│   ├── listen2.py              # Serves editor + renderers, hot-reloads the script (stdlib only)
│   ├── listen2/
│   │   ├── editor.html         # The hub: clock, mic, FRP engine, per-world state, word stepping
│   │   └── api-docs.html       # Live command reference (also embedded as the editor's Docs sidebar)
│   ├── listen.py               # Legacy speech listener (Vosk/Whisper) — not wired into the editor
│   ├── serve.py                # Legacy WebSocket relay — not used by the editor
│   └── recognizers/            # Vosk / Whisper speech modules (+ models)
├── interpreters/
│   └── browser/
│       ├── browser_2d.html     # Dumb 2D renderer (Paper.js)
│       ├── browser_3d.html     # Dumb 3D renderer (Three.js)
│       ├── api_2d.js           # browser_2d.* verbs
│       ├── api_3d.js           # browser_3d.* verbs
│       ├── frp.js              # Shared FRP engine (dynamic props, tweens, approach)
│       ├── interpreter_core.js # applyOps receiver / shared renderer plumbing
│       └── colors.js           # Named color map
└── tests/                      # Example scripts — see tests/README.md
```

## Troubleshooting

- **Nothing renders / renderers are blank.** They only draw while the editor is driving them. Make sure you're viewing the editor at `http://localhost:8100`, not a renderer file on its own.
- **No audio reactivity.** Allow the mic when prompted and click once in the page so the audio context can start. Also confirm your reactive command is a continuous `[ ... ]` bracket, not `[! ... ]`.
- **Assets won't load.** The renderers need internet access for the Paper.js / Three.js / CodeMirror CDNs.
- **A continuous effect won't stop or a later tween won't take.** That's the stickiness of continuous brackets — restart (Ctrl + ↑), or drive the property from a mutable `let` you flip with one-shots.

## Credits

Paper.js (2D vector graphics) · Three.js (3D) · CodeMirror (editor) · Vosk and OpenAI Whisper (speech recognition, for the voice-driven path).
