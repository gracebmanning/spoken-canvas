# Plan: Centralize scripting + FRP engine in the editor

## Status
Phase 1 (below) is ready to implement. Phases 2–3 are documented for context and
future work only — **do not implement them in this pass.** Do not commit or push
without being asked; just get the working tree into a working, verified state.

## Why

Today, when a script command like `[browser_2d: let c = circle(50,"red")]` runs,
the *code text* is shipped over `postMessage` to the `browser_2d` iframe and
`eval`'d there — that iframe has its own copy of the animation engine
(`frp.js`) and its own copy of the verb functions (`circle`, `move`, `rotate`, ...),
and holds the real Paper.js/Three.js objects.

We want two future capabilities this doesn't support well:
1. **Continuous, self-updating commands** — a bracket that re-evaluates every
   frame instead of once, e.g. a shape whose kind or properties are themselves a
   function of time, without duplicating objects each frame (a reconciliation
   problem, like React's).
2. **Cross-world reactive reads/writes** — e.g. a hypothetical `particles` world
   reading `browser_2d`'s current circle position every frame
   (`particles.setGravityAt(browser_2d.circle.location)`), or creating/updating
   objects in another world.

Building both on top of today's architecture means routing code (or worse,
serialized calls) between iframe realms — awkward relay-of-relay message
passing, especially for (2).

**The fix: stop evaluating script code inside the iframes at all.** Move the verb
functions and the FRP engine into the editor's own JS realm. Each iframe becomes
a "dumb" renderer: it receives a small list of `{id, kind, props}` operations
once per frame and applies them to native Paper.js/Three.js objects — it never
sees script text, never calls `eval`, and doesn't need `frp.js` or `colors.js`
anymore.

Once *all* verb functions and object state live in one realm (the editor), both
future capabilities above stop requiring any message-passing at all — reads and
writes to "another world's" state become plain in-process property access,
because there's only one process. This document only builds the *foundation*
(Phase 1); reconciliation and cross-world syntax are Phase 2/3, deferred.

## Current architecture (for context — verify by reading the files, this may drift)

- `listener/listen2.py` — serves `listener/listen2/editor.html` at `/`, serves
  `interpreters/browser/*` (browser_2d.html, browser_3d.html, colors.js, frp.js,
  interpreter_core.js) under `/interpreters/`, serves the `.script` file and an
  SSE hot-reload stream. No WebSocket relay (already removed).
- `listener/listen2/editor.html` — CodeMirror editor + word tracker. Owns the
  single master clock (`tick(nowMs)` computes `t`/`dt`) and the microphone (RMS
  meter → `audioLevel`). Every `requestAnimationFrame`, posts
  `{type:"tick", ctx:{t, dt, audioLevel}}` to both iframes. When the listener
  lands on a bracketed command, parses `[world: code]` (or bare `code`, default
  target `browser_2d`) and posts `{type:"execute", code}` to that one iframe via
  `TARGET_FRAMES[target].contentWindow.postMessage(...)`.
- `interpreters/browser/colors.js` — `COLOR_MAP` + `parseColor(str)`, attached to
  `window`.
- `interpreters/browser/frp.js` — the animation engine, attached to `window`:
  `dynamicProps` (Map<item, Map<path, fn(ctx)=>value>>), `registerDynamic`/
  `unregisterDynamic`, `setPath`/`getPath` (dot-path get/set on any object),
  `compileExpression`, `buildContext()` (returns cached `{t, dt, audioLevel}`),
  `applyTick(ctx)` (updates the cache, then calls `tickDynamicProps()`),
  `toDynamicFn` (normalizes number|string|function into a `(ctx)=>value` fn),
  `easeOutCubic`, `registerTween` (duration-based tween, self-unregisters),
  `applyDynamic` (apply one value to one path: number snaps/tweens, string/
  function registers a continuous dynamic), `applyTransform` (3-axis version of
  `applyDynamic`, used for position/rotation/scale), `dynamicProp`/`dynamicColor`/
  `dynamicSize` (support number|string|function args on *creation* calls, e.g. a
  circle whose radius is `(c) => 50 + c.t`), `audioBaseScale` (WeakMap, used by
  `scale()`/`audio_reactive()` to remember the pre-audio-reactive scale).
- `interpreters/browser/interpreter_core.js` — `globalizeDeclarations(code)`
  (regex-rewrites top-of-statement `let/const/var NAME =` to `window.NAME =`, so
  a handle created by one command survives into later commands),
  `executeCommand(code, {afterExecute, onError})` (indirect `eval`), and
  `connectToEditor({onExecute, onTick})` (postMessage listener dispatching by
  `msg.type`).
- `interpreters/browser/browser_2d.html` — Paper.js. Loads colors.js, frp.js,
  interpreter_core.js. Defines verb functions directly against Paper.js:
  `circle/square/rect/ellipse/arrow/line/text/box` (creators — each supports
  number|string|function args on size/color/content via `dynamicSize`/
  `dynamicColor`/`dynamicProp`), `move/rotate/scale/fade` (+ `opacity` alias) and
  `audio_reactive` (mutators, via `applyDynamic`/`registerDynamic`), `remove`/
  `clear`. `paper.settings.applyMatrix = false` (required so rotation/scaling
  are live, animatable absolute properties instead of being baked into
  geometry). `connectToEditor`'s `onTick` calls `applyTick(ctx)` then
  `view.draw()`; `onExecute` calls `executeCommand`.
- `interpreters/browser/browser_3d.html` — Three.js. Loads colors.js, frp.js,
  interpreter_core.js. Defines `cube/sphere/torus/tube/cloud` (creators, no
  dynamic-size/color support today — not added, out of scope here too),
  `move/rotate/scale/audio_reactive/color/opacity` (mutators, `rotate`/`scale`
  go through `applyTransform`, a 3-axis wrapper over `applyDynamic`; `rotate`
  converts degrees→radians), `noise` (drifts raw vertex-buffer positions using a
  sin/cos field parameterized by `t` — **not** representable as a few scalar
  properties; see "vertex noise" note below), `remove`/`clear`.
  `connectToEditor`'s `onTick` calls `applyTick(ctx)`, then
  `updateVertexNoise(ctx.t)`, then `renderer.render(scene, camera)`.

## Phase 1 goal (build this now)

1. `circle`, `square`, `rect`, `ellipse`, `arrow`, `line`, `text`, `box`, `cube`,
   `sphere`, `torus`, `tube`, `cloud`, `move`, `rotate`, `scale`, `fade`/
   `opacity`, `color`, `audio_reactive`, `noise`, `remove`, `clear` all become
   **editor-level** functions. They operate on a plain per-world state store,
   not on Paper.js/Three.js objects, and return a lightweight handle, not a
   native object.
2. The FRP engine (`frp.js`) is loaded and runs **only** in the editor now. It
   ticks the state store's props, not native objects. (Its code should need
   almost no changes — `setPath`/`getPath`/`registerDynamic`/tween all already
   operate generically on "any object with dot-paths," so pointing them at
   plain state objects instead of live Paper/Three objects should mostly just
   work.)
3. `colors.js` also moves to being loaded only by the editor — colors resolve
   to hex **once**, in the editor, and the resolved hex string is what's sent
   down. Worlds never call `parseColor`.
4. Once per tick, after the editor resolves every object's current props, it
   sends each world a message like:
   ```
   {type: "applyOps", t, ops: [{id, kind, props}, ...], removed: [id, ...]}
   ```
   `ops` is the *full current state* of every live object for that world (not a
   diff — there are only ever a handful of shapes; don't build diffing yet,
   that's premature). `removed` lists ids destroyed since the last tick. `t` is
   still included even though the world no longer owns the clock — see "vertex
   noise" below for why.
5. Each world (`browser_2d.html`/`browser_3d.html`) shrinks to: scene/camera/
   renderer or Paper setup, window resize handling, a **generic per-`kind`
   apply-dispatcher** (given `{id, kind, props}`: if `id` is unseen, construct
   the right native object for `kind` and cache it by id; if seen and `kind`
   unchanged, update the native object's settable properties from `props`; if
   seen and `kind` changed — not expected in Phase 1 since nothing recreates
   ids yet, but handle it defensively by destroying and reconstructing anyway),
   destruction of ids in `removed`, and (3D only) the native vertex-noise loop.
   They **no longer** define `circle`/`move`/`rotate`/etc. as script-facing
   functions, no longer call `eval`, and no longer load `colors.js`/`frp.js`/
   `interpreter_core.js`'s `executeCommand`.
6. Bracket command **routing and timing stay exactly as they are today** —
   one-shot execution when the listener lands on the word, single target per
   bracket, `[world: code]` colon syntax (or bare code defaulting to
   `browser_2d`). The only thing that changes is *where* `code` evaluates:
   the editor, against that world's namespace object (see "variable isolation"
   below) — not inside that world's iframe.
7. `let x = ...` promotion (currently `globalizeDeclarations` → `window.x = ...`)
   must still work, but **scoped per target world** — see "variable isolation."

### Explicitly deferred (do not build — documented for later)

- **Phase 2: continuous/reconciled brackets.** A bracket written as a function
  gets re-invoked every tick instead of once. Needs an identity scheme (likely
  keyed by `(bracket source position, let-binding name)`) so re-invoking
  `let x = someCreator(...)` updates the existing object in place instead of
  creating a new one each frame, with a type-change (e.g. `someCreator` itself
  changes from `circle` to `square` between frames) triggering destroy +
  recreate. Update-in-place should be implementable by translating new args into
  the same `move`/`color`/resize logic Phase 1 already needs for mutators — do
  not build a second "update mode" per creator from scratch.
- **Phase 3: cross-world dot-syntax and reactive reads/writes**, e.g.
  `particles.setGravityAt(browser_2d.circle.location)`. Once Phase 1 lands,
  `browser_2d` can literally *be* the per-world namespace object introduced for
  variable isolation (see below) — reading `browser_2d.circle.location` becomes
  a plain property read in the same realm, no message passing. This should
  fall out of Phase 1 almost for free; do not build extra plumbing for it now.
- **Escape hatch for raw Paper.js/Three.js access.** Today both worlds
  deliberately expose their native library (`window.THREE`, `window.scene`,
  `window.paper`, `window.Path`, ...) for when a verb function isn't enough.
  Centralizing eval in the editor removes this, since the editor never loads
  Paper.js/Three.js and native objects can't cross the postMessage boundary
  anyway. Nothing in `tests/stephen/main.script` uses this today. If it's
  needed later, the likely fix is a second, separate bracket form that still
  evals locally in one target world (coexisting with the new centralized path),
  not a compromise to the centralized model. Do not build this now — just don't
  accidentally foreclose it either.

## Key design decisions (read before implementing)

### Variable isolation across worlds — use `with`

If all script code evaluates in one shared editor realm, `[browser_2d: let x =
...]` and `[browser_3d: let x = ...]` would collide in a single `window.x`
today's per-iframe isolation currently prevents for free. Fix: give each world
a plain object (`const worlds = { browser_2d: {}, browser_3d: {} }`), and
evaluate each bracket's code with:

```js
with (worlds[target]) {
    (0, eval)(globalizeDeclarationsForWith(code));
}
```

where declarations are rewritten to plain assignment (`let x = ...` → `x = ...`,
*not* `window.x = ...`) so `with` resolves them onto `worlds[target]`. This
works because `with` binds bare identifier reads/writes to properties of the
given object when eval'd in **non-strict** mode — verify the editor's inline
`<script>` block has no `"use strict"` pragma and isn't a module (it isn't,
today). `with` is normally discouraged in application code, but this is a
live-coding DSL evaluating short, non-minified, non-performance-critical
snippets — the usual objections (minification, hard static analysis, perf)
don't apply. This also happens to make `worlds.browser_2d.circle` a plain
property read, which is exactly the shape Phase 3 needs later — a bonus, not
the point of doing it now.

### The `id`/`kind`/`props` state store

Per world: `Map<id, {kind, props}>`. `id` can just be a per-world incrementing
counter for Phase 1 (nothing recreates ids yet, so collision/reconciliation
isn't a concern this phase — but don't paint yourself into a corner; keep id
generation as an isolated one-line function so Phase 2 can swap it for the
position+binding-name scheme later). Creator verbs (`circle`, `cube`, ...)
allocate a new id and entry; mutator verbs (`move`, `rotate`, `scale`, `fade`/
`opacity`, `color`, `audio_reactive`, `noise`) look up an existing id (via the
handle passed in) and modify its `props`; `remove` deletes the entry and
records the id for the next `removed` list; `clear` deletes every entry for
that world and records them all as removed.

Handles returned to script code should be small and stable, e.g. `{__world,
__id}` — enough for a mutator call like `move(c, 100, 0)` to find the right
map entry, but not a native object.

### Argument resolution (number | string expression | function) is unchanged

`frp.js`'s existing `applyDynamic`/`dynamicSize`/`dynamicColor`/`dynamicProp`
already normalize number/string/function arguments into `(ctx) => value`
functions and register them against `dynamicProps`. None of that logic needs to
change — only what it's pointed at changes (a plain props object's paths,
instead of `mesh.position.x` or `item.scaling.x`). Verb functions should still
accept the same argument shapes they do today (e.g. `rotate(shape, "t*60")`
should keep working exactly as it does now).

### Vertex noise stays local to the 3D world — this is the one exception

3D's `noise(shape, intensity)` mutates a raw per-vertex Float32Array every
frame using a sin/cos field driven by `t`. This does not reduce to "a few
scalar properties" — it's a native, high-frequency, large-data effect, and
routing per-vertex buffers through the editor every frame would be wasteful and
pointless. Keep this local:
- Editor-level `noise(shape, intensity)` just sets `props.noiseIntensity` on
  the state-store entry (a single number) — cheap, uniform with every other
  verb.
- The 3D world's apply-dispatcher, on seeing `props.noiseIntensity` for a given
  native mesh, manages its own local `vertexNoise` Map exactly as today
  (`updateVertexNoise(t)`), using the `t` value included in the `applyOps`
  message.
- This is the template for any *future* similarly-native effect: if it reduces
  to a handful of scalar/string properties, compute it in the editor and ship
  the resolved value; if it's inherently a native, high-frequency, or
  large-data operation, keep the animation loop local to the world,
  parameterized by a small number of props the editor still tracks, using the
  ambient `t` the editor still provides for exactly this purpose.

### Script paths from editor.html

`editor.html` is served at `/`. `colors.js`/`frp.js` are served under
`/interpreters/` (see `listen2.py`'s `_serve_interpreter_file`). Because
`browser_2d.html`/`browser_3d.html` are themselves served at
`/interpreters/browser_2d.html`, their existing `<script src="colors.js">`
(relative) resolves correctly today. `editor.html` is served at a different
base path, so its script tags for the same files **must use the absolute path**:
`<script src="/interpreters/colors.js"></script>` and
`<script src="/interpreters/frp.js"></script>`. Getting this wrong is a silent
404, not a crash — check the browser network tab / console during
verification.

## File-by-file task list

1. **`interpreters/browser/frp.js`** — verify it needs no changes (it shouldn't;
   its functions are already generic over "any object with dot-paths"). If any
   function assumes something Paper/Three-specific, generalize it.
2. **`listener/listen2/editor.html`**:
   - Add `<script src="/interpreters/colors.js"></script>` and
     `<script src="/interpreters/frp.js"></script>` in `<head>`, before the
     inline `<script>` block (CodeMirror's own scripts can stay where they are).
   - Add the `worlds = { browser_2d: {}, browser_3d: {} }` namespace objects.
   - Add the per-world state store (`Map<id, {kind, props}>`) and id allocator.
   - Port `circle/square/rect/ellipse/arrow/line/text/box` (from
     `browser_2d.html`) and `cube/sphere/torus/tube/cloud` (from
     `browser_3d.html`) as editor-level functions writing into the 2D/3D state
     stores respectively — reuse the existing `dynamicSize`/`dynamicColor`/
     `dynamicProp` argument-handling logic verbatim, just targeting state-store
     props instead of Paper/Three objects.
   - Port `move/rotate/scale/fade`/`opacity`/`color`/`audio_reactive`/`noise`/
     `remove`/`clear` similarly. Note 2D and 3D currently differ slightly here
     (2D has no `color()`, 3D's `rotate` does 3 axes + deg→rad, 2D's `rotate` is
     a single scalar in degrees already) — preserve those differences, don't
     force a unified signature.
   - Replace `sendCommand`'s postMessage-of-raw-code with: look up `worlds[target]`,
     eval `code` in that `with` scope (see above), same triggering logic
     (`executeCommandToken`/`moveWord` unchanged).
   - Extend the per-tick loop: after computing `ctx`, call `tickDynamicProps()`
     (now ticking the state-store props), then build and post
     `{type:"applyOps", t: ctx.t, ops, removed}` to each iframe (instead of/in
     addition to the existing `{type:"tick", ctx}` — decide whether 3D still
     needs the raw tick message for anything now that it doesn't run
     `applyTick` itself; likely `applyOps` fully replaces it since `t` rides
     along in the new message).
   - `restart()`/`clear` handling must also clear the editor-side state stores
     (not just reload the iframes), so ids don't leak across a restart.
3. **`interpreters/browser/browser_2d.html`**:
   - Remove `circle/square/rect/ellipse/arrow/line/text/box/move/rotate/scale/
     fade/opacity/audio_reactive/remove/clear` and all their JSDoc.
   - Remove the `<script>` includes for `colors.js`, `frp.js`, and
     `interpreter_core.js`'s `executeCommand` usage (keep `connectToEditor` if
     you keep using it for the new message type, or replace with a plain
     `window.addEventListener("message", ...)` if `connectToEditor`'s
     execute/tick-shaped API no longer fits — your call, keep it minimal).
   - Add a generic `applyOps({t, ops, removed})` handler: for each op, look up
     or construct the native Paper.js object for `kind`, update its settable
     properties (`position`, `rotation`, `scaling`/radius-as-scale trick,
     `fillColor`/`strokeColor`, `opacity`, `content`) from `props`, keyed by
     `id`. Destroy native objects for ids in `removed`. Call `view.draw()` once
     after applying.
   - Keep `paper.settings.applyMatrix = false` and the Paper setup.
4. **`interpreters/browser/browser_3d.html`**:
   - Remove the verb functions (`cube/sphere/torus/tube/cloud/move/rotate/
     scale/audio_reactive/color/opacity/remove/clear`) and their JSDoc.
   - Remove `colors.js`/`frp.js` includes and `executeCommand` usage, same as
     2D.
   - Add the generic `applyOps({t, ops, removed})` handler, dispatching per
     `kind` to construct/update the right `THREE.Mesh`/`THREE.Points`. Rotation
     props arrive already in radians (converted at the editor level) or still
     need conversion here — **decide and document which**, then keep it
     consistent with 2D's approach.
   - Keep `updateVertexNoise`/`vertexNoise` local (see design decision above),
     driven by `props.noiseIntensity` and the `t` included in `applyOps`.
   - Keep scene/camera/renderer/lights setup and the resize handler.
5. **`interpreters/browser/interpreter_core.js`** — `executeCommand`/
   `globalizeDeclarations` are likely no longer used by the worlds at all after
   this change (only possibly by the editor, in a modified form for the `with`
   scoping — consider whether the editor needs its own small variant instead of
   reusing this file). Decide whether this file becomes editor-only, split, or
   trimmed to just whatever's still shared. Don't leave dead exports behind.
6. **`interpreters/browser/colors.js`** — no code changes expected; it just
   moves to being loaded by the editor instead of by each world.

## Verification checklist

- [ ] `python -m py_compile listener/listen2.py` (should be untouched, but
      confirm).
- [ ] Load the editor, open both iframes' devtools consoles: confirm no 404s
      for script includes, no `ReferenceError`s.
- [ ] Run through `tests/stephen/main.script` end to end: cube creation +
      continuous rotation (`"t * 15"`/`"t * 20"` string-expression args still
      work), circle creation + color swap, confirm shapes render and animate.
- [ ] Confirm `let`-bound names survive across commands *within* one world
      (e.g. create `c1` in one bracket, `move`/`color` it in a later bracket
      targeting the same world).
- [ ] Confirm two different worlds can each use the same variable name (e.g.
      `c` in a `browser_2d` bracket and `c` in a `browser_3d` bracket) without
      colliding.
- [ ] Confirm `RESET()` / restart (`ArrowUp`) clears both the editor's state
      stores and both worlds' native objects — no leaked shapes after restart.
- [ ] Confirm audio-reactive scaling and vertex noise (3D) still animate
      correctly, since both depend on values now computed/relayed differently.
- [ ] Re-read `frp.js` after porting to confirm it wasn't quietly duplicated
      instead of shared — there should be exactly one copy of the engine, and
      it should be the one loaded by the editor.
