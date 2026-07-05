# Plan: Phase 2 — continuous brackets, guarded tweens, explicit namespacing

## Status

Builds on Phase 1 (`listener/FRP_CENTRALIZATION_PLAN.md` — **done and verified**:
verb functions + the FRP engine run only in the editor; `browser_2d.html`/
`browser_3d.html` are dumb `{id, kind, props}` renderers driven by
`{type:"applyOps", t, ops, removed}` messages). This document is ready to
implement. Do not commit or push without being asked.

Two acceptance scripts already exist and should drive verification — **read
both in full before writing any code**, they are the concrete spec:
- `tests/stephen/new_api.script`
- `tests/stephen/main.script`

Both were iterated on carefully and should be treated as correct; if you think
one of them is wrong, stop and report why rather than "fixing" it. Notable
conventions they establish, all deliberate:
- **Plain `[code]` (continuous) brackets are the default**, used even for
  ordinary static creation like `cube(1.2, 1.2, 1.2, "gray")`. `[!code]`
  (one-off) is a narrow exception, used only for `audio_reactive` setup and
  `clear()` — see section C.
- **No string-expression arguments anywhere** (no more `"t * 15"`). Time/audio-
  driven values are written as ordinary expressions or, where required,
  zero-argument functions — see section B.
- **No `c`/`ctx` parameter anywhere.** Time, mic level, and script-progress are
  read from ambient namespace objects — `TIME.t`, `TIME.dt`,
  `MIC.audio_level`, `SCRIPT.words_completed()` — never passed as a function
  argument. This is the biggest change from earlier drafts of this plan; see
  section B, it is not optional polish.
- `main.script`'s growing-circle line
  (`circle(() => 50 * MIC.audio_level + TIME.t, ...)`) is the main regression
  check for the `dynamicSize` guard in section E — read that section before
  touching `frp.js`, it explains a serious, easy-to-miss bug this exact line
  will hit if the guard is missing or wrong.

## Why

Phase 1 preserved Phase 1's bracket model as-is: one-shot execution,
`[world: code]` colon-prefix routing to a single target per bracket. Scoping
discussion since then (see git history / prior conversation — not re-derivable
from files alone, so trust this document) converged on four changes:

1. **Some behavior should be able to persist and update over time as a single
   unit** — e.g. a shape whose *kind* (not just its properties) depends on
   live time, such as swapping from a circle to a square at `t=10`. This can't
   be expressed by Phase 1's per-argument dynamics (`(ctx) => value`), which
   only make individual *arguments* dynamic, not the *choice of which creator
   function runs*.
2. **World targeting should be explicit in the code, not annotated on the
   bracket.** `[browser_2d: code]` picks a single implicit target for the whole
   bracket; the desired model is `browser_2d.circle(...)` / `browser_3d.cube(...)`
   as ordinary, explicit namespaced calls, with no bracket-level target concept
   at all. A useful side effect: brackets that touch multiple worlds at once
   become trivially expressible, with no special mechanism needed for it.
3. **Duration-based tweens must survive being re-invoked** (a consequence of
   (1) — a bracket that runs every tick can't use `move(x, 100, 0, 2)` as-is,
   since re-invoking a tween every tick perpetually restarts it and it never
   completes).
4. **Time/audio/script-progress should be ambient, not parameters.** An
   earlier draft of this plan threaded a `c`/`ctx` parameter through every
   continuous bracket (`(c) => { ... c.t ... }`) and required wrapping
   individual arguments in `(c) => ...` to make them time-varying. This turned
   out to be both redundant (a continuous bracket already re-runs every tick —
   wrapping an argument *inside* it in another per-tick function is a second,
   pointless layer) and inconsistent (a helper function defined in one bracket
   and called from another had to have `c` threaded through it explicitly to
   avoid reading a stale value). Exposing `TIME`, `MIC` (and later other
   sensors, e.g. a hypothetical `WEBCAM_CV`) as persistent, ambient namespace
   objects — mutated in place once per tick, read directly wherever needed —
   removes both problems at once and generalizes cleanly to future sensor
   sources without changing how any of them are read. See section B.

## Current architecture (Phase 1, as built — verify against files, this may drift)

- `listener/listen2/editor.html` owns: the master clock (`t`/`dt`), the
  microphone (`audioLevel`), the FRP engine (`frp.js`), and `colors.js`/
  `parseColor`. Also owns a per-world state store (`stateStores:
  {browser_2d: Map<id,{kind,props}>, browser_3d: Map<...>}`) and the verb
  functions (`circle`/`square`/.../`move`/`rotate`/.../`clear`), built by
  `makeWorld2DApi`/`makeWorld3DApi` and attached as **prototypes** of per-world
  namespace objects (`worldApis.browser_2d`, `worldApis.browser_3d`).
- **`frp.js`'s current (Phase 1) shape — this is what section B changes**:
  a per-frame **ctx object** is the whole mechanism. Private module state
  `_t`/`_dt`/`_audioLevel` is cached by `applyTick(ctx)` (called once per tick
  by `editor.html`, passed `{t, dt, audioLevel}`); `buildContext()` bundles
  that private state back into a fresh `{t, dt, audioLevel}` object;
  `tickDynamicProps()` calls `buildContext()` once and samples every
  registered dynamic as `fn(ctx)`; `registerTween`/`applyDynamic`/
  `dynamicProp`/`dynamicColor`/`dynamicSize`/`toDynamicFn` all take or produce
  `(ctx) => value` functions and read `ctx.t`/`ctx.audioLevel`. **All of this
  ctx-object machinery is removed in section B** — dynamics become
  **zero-argument** functions (`() => value`) that read `TIME.t`/
  `MIC.audio_level` directly, since those are now persistent objects any
  closure can reference without anything being passed in.
- **Bracket routing today**: `splitCommandTarget(content)` reads a `world:`
  prefix (or falls back to `DEFAULT_TARGET = "browser_2d"`), then
  `evalInWorld(target, code)` does:
  ```
  const worldObj = worlds[target];              // Object.create(worldApis[target])
  const rewritten = globalizeDeclarationsForWith(code, worldObj); // let x = ... -> x = ...
  with (worldObj) { eval(rewritten); }
  ```
  `worlds[target]` is a *fresh* `Object.create(worldApis[target])` per world,
  reset by `resetWorldState()` (called at load and by `restart()`). Verb
  functions are found via `with`'s prototype-chain walk; `let`-bound user
  variables become **own** properties of `worlds[target]`, so `restart()` can
  wipe user state without losing the verb functions.
  **This whole per-world-`with`-scope mechanism goes away in Phase 2** — see
  section A.
- Bracket execution is currently always one-shot: `eval(rewritten)` runs once,
  its result is discarded, nothing is registered to run again.
- `tick(nowMs)` (the master `requestAnimationFrame` loop) currently builds
  `ctx = {t, dt, audioLevel}`, calls `applyTick(ctx)` (advances every
  registered dynamic across both worlds' state stores), then posts each
  world's *full current state* down as `applyOps`. Under Phase 2, `tick()`
  instead **mutates** `TIME.t`/`TIME.dt`/`MIC.audio_level` in place, invokes
  the continuous-bracket registry (section D), then calls `tickDynamicProps()`
  (no ctx passed) — see section B for the full sequence.
- Each world (`browser_2d.html`/`browser_3d.html`) is a generic per-`kind`
  apply-dispatcher; **nothing in this document requires changing either of
  them** — Phase 2 is entirely an editor-side (and `frp.js`-side) change. The
  `applyOps` message's own `t` field (used by 3D's vertex-noise loop) is
  unrelated to `TIME.t` below — it's an existing, separate protocol field for
  world-side rendering, unaffected by this change; editor.html just continues
  to include its locally-computed `t` in that message as it already does.

## Phase 2 goal

### A. Explicit world namespacing — replaces bracket-level `[world: code]` routing

- **One shared script-level scope**, not one per world. Call it `scriptScope`.
- `worldApis.browser_2d` / `worldApis.browser_3d` (already built in Phase 1,
  unchanged) become **properties of `scriptScope`** — i.e.
  `scriptScope.browser_2d = worldApis.browser_2d`,
  `scriptScope.browser_3d = worldApis.browser_3d` — reached only via
  `browser_2d.circle(...)` / `browser_3d.move(...)`. **No verb function is ever
  bare-reachable.** This is not optional for verbs that exist in both worlds
  (`move`/`rotate`/`scale`/`remove`/`clear`/`audio_reactive` all exist in both
  APIs with different signatures) — a flat scope literally cannot have two
  functions sharing one name, so the prefix is the only way to disambiguate
  once there's no per-bracket target choosing which one you meant.
- `let`-bound user variables become own properties of `scriptScope` directly
  (same `globalizeDeclarationsForWith`-style pre-declare-then-plain-assign
  mechanism from Phase 1, just targeting one object instead of `worlds[target]`).
  Reusing a variable name across a 2D and a 3D creation in separate brackets is
  fine — it's just normal variable reuse, not a collision to guard against;
  `resolveHandle`'s existing `handle.__world !== world` check still catches
  genuine misuse (passing a 2D handle into a 3D verb) with a clear error.
- Remove `splitCommandTarget`, `DEFAULT_TARGET`, and `INTERPRETER_TARGETS`-as-a-
  routing-list entirely. `TARGET_FRAMES` (the iframe DOM elements) is still
  needed for posting `applyOps` — that's unrelated to script routing and
  doesn't change.
- A bracket's content is now just `code` (see form C below) — no colon-prefix
  parsing of any kind.
- `restart()` rebuilds **one** fresh `scriptScope` (re-populating
  `browser_2d`/`browser_3d`/`TIME`/`MIC`/`SCRIPT` — see section B — from their
  persistent sources, wiping user `let`-bindings), in addition to resetting the
  state stores (unchanged from Phase 1) and clearing the continuous-bracket
  registry (new — see section D).
- Minor known footgun, not worth guarding against: a script could shadow
  `browser_2d`/`browser_3d`/`TIME`/`MIC`/`SCRIPT` via e.g. `let TIME = ...`.
  Same class of self-inflicted footgun as any global shadowing in JS; do
  nothing special about it.

### B. Ambient `TIME`/`MIC`/`SCRIPT` namespaces — no `c`/`ctx` parameter anywhere

This is the section that changes `frp.js` most. Read it fully before touching
that file.

- **`TIME` and `MIC` are owned by `frp.js`**, exported as persistent, mutable
  objects (not rebuilt each tick — the *same* object is mutated in place, so
  anything holding a reference to `TIME` always sees current values):
  ```
  const TIME = { t: 0, dt: 0 };
  const MIC = { audio_level: 0 };
  window.TIME = TIME;
  window.MIC = MIC;
  ```
  `editor.html`'s `tick(nowMs)` writes into them directly —
  `TIME.t = ...; TIME.dt = ...; MIC.audio_level = ...;` — instead of building
  a `ctx` object and passing it anywhere. Both become properties of
  `scriptScope` (`scriptScope.TIME = TIME; scriptScope.MIC = MIC;`), reached
  from script code the same way `browser_2d`/`browser_3d` are.
- **`SCRIPT` is owned by `editor.html`**, not `frp.js` — it's about
  script/word-navigation state, unrelated to the animation engine:
  ```
  const SCRIPT = {
    words_completed: () => words.slice(0, wordIndex).filter((w) => !w.cmd).length,
  };
  ```
  `words_completed` is a **function**, not a property, deliberately: (a) it's
  a real computation (spoken words only, excluding bracket/command tokens —
  not a 1:1 mirror of the raw `wordIndex`), and (b) as a closure over the
  existing `words`/`wordIndex` variables, it needs zero changes to the
  existing word-tracking code (`moveWord`/`refreshMark`) to stay correct — no
  separate property to remember to keep in sync. `TIME`/`MIC` don't share this
  argument (their canonical values are already computed fresh inside the
  per-tick loop, so mutating a plain property there is free, not an extra
  sync step) — that's why they're properties and `SCRIPT.words_completed` is a
  method. Don't generalize one shape onto the other.
- **Every dynamic in `frp.js` becomes a zero-argument function.** This is a
  mechanical but pervasive rewrite:
  - `_t`/`_dt`/`_audioLevel` (private cached state) and `buildContext()` are
    **removed entirely** — nothing needs to reconstruct a ctx object anymore,
    since `TIME`/`MIC` themselves are the persistent state.
  - `applyTick(ctx)` → either remove it and have `editor.html` call
    `tickDynamicProps()` directly, or keep the name as a zero-arg pass-through
    (`function applyTick() { tickDynamicProps(); }`) for continuity — your
    call, just make sure nothing still expects to pass it a ctx argument.
  - `tickDynamicProps()`: samples each registered dynamic as `fn()` (no
    argument), not `fn(ctx)`.
  - `registerTween`: `const startT = TIME.t;` (was `_t`); the registered
    dynamic becomes `() => { const now = TIME.t; ... }`.
  - `applyDynamic`: the string/function branch registers `() =>
    valueTransform(fn())` (was `(ctx) => valueTransform(fn(ctx))`).
  - `toDynamicFn`: a function argument is returned as-is (unchanged), but is
    now expected to be zero-arg and to read `TIME`/`MIC` itself. The **legacy
    string-expression path** (`compileExpression`, still supported for
    backward compatibility even though neither acceptance script uses it
    anymore) changes from `(ctx) => compiled(ctx.t)` to `() =>
    compiled(TIME.t)`.
  - `dynamicProp`: `const base = arg();` (was `arg(buildContext())`);
    registered dynamic becomes `() => transform(arg())`.
  - `dynamicColor`: unchanged itself (delegates to `dynamicProp`).
  - `dynamicSize`: `const base = fn() || 1;` (was `fn(buildContext())`);
    registered dynamic becomes `() => fn() / base` — **and this is exactly
    where the guard from section E must live**, read that section before
    implementing this.
- **What this means for scripts** (already reflected in both acceptance
  scripts — this is descriptive, not something to change): inside a
  continuous bracket, anything the world *re-reads every apply* (position,
  rotation, opacity, color, text content) can be written as a **bare
  expression** using `TIME.t`/`MIC.audio_level` directly —
  `browser_3d.rotate(block, TIME.t * 15, TIME.t * 20, 0)` — no wrapper
  function needed, since the bracket itself already re-runs every tick. The
  **one exception**: 2D creators' size/radius/width/height arguments still
  need an explicit zero-arg wrapper — `circle(() => 50 + TIME.t, "red")` —
  regardless of bracket continuity, because that's the only path that reaches
  `dynamicSize`'s ongoing scaling mechanism at all (Paper.js bakes a circle's
  radius into its geometry at construction and never re-reads it — a bare
  number there only ever sets the fixed initial size). A stored helper
  function shared across multiple brackets (e.g. `main.script`'s
  `let x = () => (10 * MIC.audio_level)`, called later as `x()`) is a
  legitimate, different case — it's zero-arg for the same reason (reads
  ambient state directly, nothing to pass in), not because it's "dynamic
  sizing."

### C. Two bracket forms — `[code]` is the default, `[!code]` is a narrow exception

- **`[code]`** (no bang) — **continuous, and this is the default form**. Use
  this for ordinary creation and mutation — `circle(...)`, `cube(...)`,
  `move(...)`, `rotate(...)` — even when the arguments are perfectly static.
  Reconciliation (section D) and the guarded tween (section E) exist
  specifically so that re-running an unchanged creation or tween every tick is
  cheap and safe, not just "technically correct" — the point is that authors
  shouldn't have to think about which form to reach for in the common case.
  Wrap it as `() => { code }` (no parameter — see section B), evaluate
  **once** (against `scriptScope`) to produce a function value, then register
  that function — keyed by the bracket's stable source position (reuse the
  `{from, to}` offsets `computeWords()` already computes for the token) — to
  be invoked every tick, forever, from the moment it's triggered, until
  `restart()` or until the *same* bracket is re-triggered (which just
  replaces the registration — **no cleanup of whatever it previously created
  is required**; a re-landed continuous bracket may leave orphaned objects
  behind, same as Phase 1's one-shot `let c1 = circle(...)` already orphans
  the previous `c1` on re-trigger today — this is accepted, not a regression,
  and explicitly not being solved in this phase).
- **`[!code]`** — **one-off, an escape hatch, not the default.** Evaluate
  `code` once against `scriptScope`, exactly like Phase 1's one-shot semantics
  (discard the result; no reconciliation; no registration). Reach for this
  only when continuous re-invocation would be semantically wrong or pointless
  to leave running — concretely, in this codebase: `remove()`/`clear()` (an
  action, not a state to maintain), and one-time setup like `audio_reactive`
  (it registers its own ongoing dynamic on first call and gains nothing from
  being re-invoked). **Do not reach for `!` to avoid thinking about tweens or
  reconciliation** — both are designed to work correctly inside plain
  continuous brackets; needing `!` to make a tween or a creation call behave
  would mean section D or E has a bug, not that the script did something
  wrong.
- There is no third "smart" form and no detection based on what `code`
  evaluates to — just these two, chosen purely by the presence or absence of
  the leading `!`.
- `executeCommandToken` (in `editor.html`) parses the bracket, trims, checks
  for a leading `!` to choose between the two paths above. This replaces
  today's `sendCommand`/`evalInWorld` single path.
- **`RESET()`**: keep it as sugar, translated into running
  `"browser_2d.clear(); browser_3d.clear();"` through the *same* one-off path
  — don't build a second, separate fan-out mechanism for it.

### D. Creator reconciliation — needed only for the continuous form

This is the mechanism that makes calling a creator function every tick safe
(doesn't spawn a new object each frame).

- **Ambient reconciliation context**: a module-level variable (or a tiny stack,
  in case of nested calls — shouldn't happen in practice but don't assume) set
  to `{bracketId, callIndex: 0}` immediately before invoking a continuous
  bracket's registered function each tick, and cleared right after. Every
  creator function increments `callIndex` each time it runs while this context
  is active.
- **Per-bracket persistent registry**: `Map<bracketId, Map<callIndex,
  {creatorFn, id}>>`. This survives across ticks — it is *not* reset each
  invocation, only when the bracket is re-registered (landed on again) or on
  `restart()`.
- Every creator function (`circle`/`square`/`rect`/`ellipse`/`arrow`/`line`/
  `text`/`box`/`cube`/`sphere`/`torus`/`tube`/`cloud`) needs a shared preamble:
  - If the reconciliation context is **not** active (called from a `[!code]`
    bracket, or from anywhere outside a continuous invocation): behave exactly
    as Phase 1 does today — always allocate a fresh id. No behavior change for
    one-off usage.
  - If active and `(bracketId, callIndex)` has **no** existing entry: allocate
    a fresh id as today, then record `{creatorFn: <this function>, id}` in the
    registry at that slot.
  - If active and the existing entry's `creatorFn` **matches** this call: do
    **not** allocate a new id. Recompute the props from the new arguments and
    write them onto the *existing* entry's `props` (this requires factoring
    each creator's "resolve arguments into a props object" logic out of the
    "allocate a new id + `store().set(id, {kind, props})`" logic, so the same
    argument-resolution code can run against an existing entry — don't
    duplicate the argument-handling logic into a second "update" implementation
    per creator). Return the **existing** handle.
    **Do not let this "recompute and write" step call `dynamicSize`'s
    `.register()` again for an already-dynamic size argument** — read section E
    before implementing this bullet, it explains a specific, serious bug this
    would otherwise (re)introduce.
  - If active and the existing entry's `creatorFn` **differs** (e.g. `circle`
    → `square`, matching `new_api.script`'s example): remove the old entry
    (same path as `remove()` — updates `removedSinceTick`, deletes from
    `dynamicProps`, deletes from the store) and allocate fresh, as if there had
    been no existing entry.
- `callIndex` resets to 0 at the **start** of each invocation of a given
  bracket's registered function, so repeated ticks produce the same sequence
  of indices as long as the same code path runs each time. A conditional that
  sometimes skips a creator call is a known limitation (same class of issue as
  React's keyless-list reconciliation) — not solved here, don't try to solve
  it, just don't let it silently corrupt state (a mismatch should be safe to
  fall back to "no existing entry, allocate fresh" rather than crash).

### E. Guards against re-registration corrupting in-flight behavior

Any registered dynamic whose *ticking formula* references a value captured at
**registration time** (a `base`, a `fromValue`) is vulnerable if that
registration is blindly repeated every tick from a continuous bracket: within
a single tick, `TIME.t`/`MIC.audio_level` don't change between the moment a
dynamic is *registered* and the moment it's *sampled* — so "start" and "now"
collapse to identical, and the formula degenerates. Two concrete cases, one of
which is a real bug you must fix, not just a theoretical concern:

1. **`dynamicSize`'s growth ratio — fix this, it is not optional.**
   `dynamicSize`'s registered dynamic is `() => fn() / base`, where `base` is
   captured once, at the moment `.register()` runs, by calling `fn()` (which
   reads `TIME.t`/`MIC.audio_level` directly per section B). Both acceptance
   scripts rely on this via a growing-circle radius argument, e.g.
   `circle(() => 50 + TIME.t, "red")`. Under Phase 2, that bracket is plain
   (continuous) by default (section C), which means its creator call is
   reconciled every tick (section D). If the reconciler's "update" path
   naively re-invokes `dynamicSize(...)` — and thus `.register()` — on every
   one of those reconciled calls, `base` gets recomputed as `fn()` (i.e.
   `50 + TIME.t` at the *current* tick) on **every tick**, and that same
   tick's `tickDynamicProps()` samples the just-registered function — which
   also reads `TIME.t` — with the exact same, unchanged-this-tick value. So
   `fn() / base` = `fn() / fn()` = **1**, every single tick. The circle would
   freeze at whatever size it happened to be instead of growing, silently,
   with no error. This is not a corner case — it is exactly what both
   acceptance scripts do, and it is exactly the kind of bug that looks fine in
   code review and only shows up when you actually watch it run (or trace it
   by hand, as this plan does above).

   **Fix**: `dynamicSize` must guard against re-registering when a dynamic is
   already active for that `(item, path)` — e.g. check
   `dynamicProps.get(item)?.has(propName + '.' + axis)` before registering,
   and skip re-registering (leaving the existing, correctly-timed registration
   running untouched) if one's already present. Put this guard **inside
   `dynamicSize` itself, in `frp.js`** — not in the reconciler or in any
   creator function. That way `dynamicSize` can safely be called every tick,
   whether from a fresh creation or a reconciled update, with no caller needing
   to know or care whether it's "the first time."

2. **Guarded tween** (`registerTween`/`applyDynamic`'s numeric+duration
   branch) — same underlying hazard, different shape. Key by `(item, path)`;
   remember the last **commanded target**. On a numeric-with-`duration>0`
   call: if the new target **equals** the currently-commanded target, do
   nothing — leave whatever's running (or already at rest) alone. If it
   **differs**, capture the *current* value (which may be mid-tween) as
   `fromValue`, start a fresh tween to the new target over `duration`, and
   update the commanded-target record. Scope this to the `duration > 0`
   branch only — snap calls (`duration === 0`) are already idempotent under
   repeat invocation (`setPath` just re-writes the same value each time), no
   guard needed there.

Both guards are pure `frp.js` changes — no verb function's call signature
changes, and no reconciliation-context awareness is needed for either, since
both are keyed purely by `(item, path)`, the same key `dynamicProps` already
uses everywhere.

### F. What does *not* need a guard — verify this claim, don't just assume it

`dynamicColor`/`dynamicProp`'s registered ticking functions are
`() => transform(arg())` — they reference no externally-captured
`base`/`fromValue` *inside* the ticking closure (any `base` they compute, e.g.
for an object's initial fill color, is used only once, at construction, and
never read again). Re-registering these every tick produces the exact same
observable result each time, so they're safe under naive repeat invocation —
confirm this by tracing it the same way section E's bug was traced, don't take
it on faith. Likewise `audio_reactive`'s base-scale capture is cached in a
`WeakMap` (`audioBaseScale`) and a second call just finds the existing base and
re-registers an equivalent dynamic — safe. Neither needs a guard or
reconciliation-context awareness; do not add call-site tracking to these, and
do not add a guard to `dynamicColor`/`dynamicProp` "to be safe" — the point of
tracing through section E's bug is to know precisely which mechanism has the
hazard (one that reads a captured value inside its own ticking formula) and
which doesn't.

## File-by-file task list

1. **`interpreters/browser/frp.js`** — the largest set of changes:
   - Remove `_t`/`_dt`/`_audioLevel` and `buildContext()`; add persistent
     `TIME = {t:0, dt:0}` and `MIC = {audio_level:0}`, exported on `window`
     (section B).
   - Convert every dynamic-producing function (`registerTween`,
     `applyDynamic`, `toDynamicFn`, `dynamicProp`, `dynamicSize`,
     `tickDynamicProps`) from the `(ctx) => ...` / `fn(ctx)` convention to
     zero-argument `() => ...` / `fn()`, reading `TIME`/`MIC` directly where
     the old code read `ctx.t`/`ctx.audioLevel` (section B — do this whole
     conversion in one pass, it's mechanical).
   - Add the existence-guard inside `dynamicSize` so it's safe to call every
     tick without re-registering an already-active dynamic (section E). **Do
     this one carefully and verify it against `main.script`'s growing-circle
     line before moving on** — it's the higher-risk, higher-consequence half
     of this file's changes.
   - Add the guarded-tween logic to `registerTween`/`applyDynamic`'s
     numeric+duration branch, keyed by `(item, path)` (section E).
   This is the only file where `frp.js` itself changes.
2. **`listener/listen2/editor.html`**:
   - Replace the per-world `worlds`/`freshWorldScope`/`resetWorldState`'s
     per-world-object logic with a single `scriptScope`, populated with
     `browser_2d`/`browser_3d` (pointing at the existing `worldApis` objects,
     unchanged from Phase 1), `TIME`/`MIC` (pointing at `frp.js`'s exported
     objects), and `SCRIPT` (defined locally, section B). `resolveHandle`, the
     state stores, and the verb-function implementations themselves
     (`makeWorld2DApi`/`makeWorld3DApi`) do **not** need to change — only how
     their namespaces are exposed to script code.
   - Remove `splitCommandTarget`/`DEFAULT_TARGET`/`INTERPRETER_TARGETS`-as-
     routing.
   - Replace `sendCommand`/`evalInWorld` with the two-form dispatch from
     section C: parse leading `!`, either one-shot-eval against `scriptScope`
     (reusing `globalizeDeclarationsForWith`, retargeted at `scriptScope`), or
     wrap-and-register (as a zero-arg function, section B) for continuous
     invocation.
   - Update `tick(nowMs)` to **mutate** `TIME.t`/`TIME.dt`/`MIC.audio_level`
     in place (not rebuild a ctx object), then invoke the continuous-bracket
     registry (inside the ambient-reconciliation-context push/pop from
     section D), then call `tickDynamicProps()` (no argument), then build and
     post each world's `applyOps` message exactly as today (still including
     its own local `t` in that message for 3D's vertex noise — see the note
     at the end of "Current architecture").
   - Add the continuous-bracket registry (a `Map` from bracket id to its
     registered zero-arg function).
   - Add the ambient reconciliation context (module-level variable) and the
     per-bracket call-site registry from section D, threaded into
     `makeWorld2DApi`/`makeWorld3DApi`'s creator functions (this does require
     touching those functions — factor out "resolve args to props" from
     "allocate id" per creator, as described in section D).
   - Update `restart()` to also clear the continuous-bracket registry.
   - Update `RESET()` handling per section C.
3. Both acceptance scripts (`tests/stephen/main.script`,
   `tests/stephen/new_api.script`) are **already updated/created** — do not
   regenerate them; if you find a genuine mistake in either (not just "it
   doesn't work yet because Phase 2 isn't built"), fix it and note why.
4. **`interpreters/browser/browser_2d.html`/`browser_3d.html`** — not expected
   to need any changes. If you find you need to touch either, that's a signal
   something in the design above is wrong — stop and report rather than
   improvising a workaround there.

## Verification checklist

- [ ] **The most important check, do this first**: with `main.script`'s
      `circle(() => 50 * MIC.audio_level + TIME.t, ...)` bracket (plain,
      continuous — no bang), confirm the circle's radius actually **keeps
      growing** over several seconds, sampled at multiple points in time, not
      just "it appears once and looks fine." If it renders once and then
      stays a fixed size, the `dynamicSize` guard (section E) is missing or
      wrong — this is the exact failure mode it silently produces. Don't rely
      on eyeballing a single frame.
- [ ] Confirm `TIME.t`/`TIME.dt`/`MIC.audio_level` are read correctly with no
      `c`/`ctx` parameter anywhere in either script's evaluated code, and that
      a bare expression using them (e.g. `browser_3d.rotate(block, TIME.t *
      15, TIME.t * 20, 0)`) updates every tick without needing a wrapper —
      confirming section B's "no wrapper needed inside a continuous bracket,
      except for `dynamicSize`" claim in practice, not just in theory.
- [ ] Confirm `SCRIPT.words_completed()` returns the count of **spoken words
      only** (excluding bracket/command tokens) at the current position, and
      that it updates correctly as the listener navigates forward/backward
      through the script via arrow keys.
- [ ] Walk through `new_api.script` end to end and confirm each narrated
      behavior: the cube persisting via reconciliation without duplicating
      (`[let block = browser_3d.cube(...)]`, no bang), rotation driven by bare
      `TIME.t`-based expressions (no wrapper, no string expressions
      anywhere), the growing circle (same guard as above), the circle→square
      swap at `t=10` with **no duplicate object** left behind (verify by
      checking the state store only ever holds one entry for that slot, not
      by eyeballing rendering alone), the position flip-flop **not restarting
      every frame** (only re-easing every 5 seconds), the mixed-world bracket
      (one bracket creating a 2D circle and pulsing a 3D mesh's opacity), and
      — the only two `[!...]` brackets in either script — audio-reactivity
      setup and the final `clear()`, both one-off by deliberate choice (see
      section C for why those two and nothing else).
- [ ] Confirm bare verb functions are **not** reachable without a world prefix
      — e.g. `[!circle(50,"red")]` should throw a `ReferenceError`, not
      silently work by falling through to some default.
- [ ] Confirm `restart()` clears the continuous-bracket registry — no
      lingering per-tick invocations trying to touch state that no longer
      exists after a restart — and that `TIME.t`/`SCRIPT.words_completed()`
      both correctly reflect a fresh start afterward.
- [ ] Confirm the two `[!...]` brackets in `new_api.script` (`audio_reactive`
      setup, `clear()`) behave as true one-shots — evaluated exactly once, no
      registration, no reconciliation touching them at all.
- [ ] `node --check` (or equivalent) on every touched file/inline script.
- [ ] Grep for dead references to the removed per-world `with`-scoping
      machinery (`worlds[target]`, `freshWorldScope`, `splitCommandTarget`,
      `DEFAULT_TARGET`, `INTERPRETER_TARGETS` used for routing) and to the
      removed ctx-object machinery (`buildContext`, `_t`, `_dt`,
      `_audioLevel`, any remaining `(ctx) =>`/`fn(ctx)` in `frp.js`).
- [ ] As with Phase 1, real Paper.js/Three.js rendering and mic capture can't
      be verified without a live browser — build a Node-based harness (as
      Phase 1's implementer did) to replay both scripts' exact commands and
      assert on the resulting state-store contents/`applyOps` payloads where
      possible, and clearly flag in the final report whatever still needs a
      live-browser pass.
