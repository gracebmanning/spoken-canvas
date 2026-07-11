/**
 * frp.js — the scene-graph animation engine. Since the FRP-centralization
 * refactor (see listener/FRP_CENTRALIZATION_PLAN.md), this is loaded and runs
 * ONLY in the editor (listener/listen2/editor.html) — the interpreter worlds
 * (browser_2d.html/browser_3d.html) no longer load it at all.
 *
 * `TIME` and `MIC` below are persistent, mutable
 * objects — the SAME object every tick, mutated in place by editor.html's
 * tick() — so any closure that captures a reference to them always reads the
 * current value with nothing threaded through as an argument. Every dynamic
 * value below is therefore a **zero-argument** function(), not function(ctx);
 * it reads TIME.t / MIC.audio_level / MIC.pitch directly wherever it used to
 * read ctx.t / ctx.audioLevel.
 *
 * Every continuous value (position, rotation, scale, opacity, color, ...) is
 * stored as a function() => value, keyed by whatever plain object owns that
 * path — e.g. a world's
 * {id, kind, props} state-store entry's `props`, not a live Paper.js/Three.js
 * object; everything below is generic over "any object with dot-paths". The
 * editor owns the clock and the microphone; once per frame it mutates
 * TIME.t/TIME.dt/MIC.audio_level/MIC.pitch itself, then calls tickDynamicProps()
 * (advancing every registered dynamic across both worlds' state stores), then
 * posts each world's fully-resolved state down as
 * {type:"applyOps", t, ops, removed} (see editor.html's tick()). A world's
 * applyOps handler just turns that into native objects and renders.
 *
 * A value can be supplied three ways wherever a world's API accepts one:
 * 1. Numeric value (tween from current value to target over 'duration' seconds)
 * 2. Function () => value (runs continuously; reads TIME/MIC itself)
 */

// item => Map of "prop.subprop" path => function() => value
const dynamicProps = new Map();

function registerDynamic(item, path, fn) {
    if (!dynamicProps.has(item)) dynamicProps.set(item, new Map());
    dynamicProps.get(item).set(path, fn);
}

function unregisterDynamic(item, path) {
    const props = dynamicProps.get(item);
    if (!props) return;
    props.delete(path);
    if (props.size === 0) dynamicProps.delete(item);
}

// read/write a nested property like "position.x" on an item.
function setPath(obj, path, value) {
    const parts = path.split('.');
    let target = obj;
    for (let i = 0; i < parts.length - 1; i++) target = target[parts[i]];
    target[parts[parts.length - 1]] = value;
}
function getPath(obj, path) {
    return path.split('.').reduce((o, k) => o[k], obj);
}


// Persistent, ambient signal objects — owned here, mutated in place once per
// tick by editor.html's tick() (TIME.t = ...; TIME.dt = ...; MIC.audio_level
// = ...;). Never rebuilt, never passed as an argument: any script closure or
// frp.js internal that holds a reference to these always sees the current
// value. See listener/FRP_PHASE2_PLAN.md section B.
const TIME = { t: 0, dt: 0 };
const MIC = { audio_level: 0, pitch: -1 };

// Normalize a continuous-value argument into a zero-argument function() => value.
// - A function is used as-is (expected to be zero-arg and read TIME/MIC itself).
// - Note: Strings are no longer permitted.
function toDynamicFn(arg) {
    if (typeof arg === 'function') return arg;
    throw "Dynamic arguments must be functions"
}

function easeOutCubic(x) {
    return 1 - Math.pow(1 - x, 3);
}

// The target most recently commanded for a given (item, path) via a
// duration>0 tween, so a continuous bracket that re-invokes the same call
// every tick doesn't perpetually restart the ease (see PHASE2 plan section E,
// part 2 — the guarded tween). item -> Map<path, targetValue>.
const tweenTargets = new Map();

// register a duration-based tween: animate 'path' from its current value to
// 'targetValue' over 'duration' seconds, then self-unregister.
function registerTween(item, path, targetValue, duration) {
    const fromValue = getPath(item, path);
    const startT = TIME.t;
    const endT = startT + duration;
    registerDynamic(item, path, () => {
        const now = TIME.t;
        if (now >= endT) {
            unregisterDynamic(item, path);
            return targetValue;
        }
        const progress = (now - startT) / duration;
        return fromValue + (targetValue - fromValue) * easeOutCubic(progress);
    });
}

// Apply one value (number | string expr | ()=>value) to one property path.
// Numbers snap (duration 0) or tween; strings/functions run continuously.
//
// Numeric tweens (duration > 0) are GUARDED, keyed by (item, path): if the
// newly commanded target is the same value already commanded last time,
// nothing happens — whatever's running (or already at rest) is left alone.
// This is what makes it safe for a continuous (non-`!`) bracket to call e.g.
// move(handle, x, y, 1) every tick without perpetually restarting the ease —
// see PHASE2 plan section E, part 2. Snap calls (duration === 0) need no
// guard: setPath just re-writes the same value each time, already idempotent.
function applyDynamic(item, path, arg, duration, valueTransform = (v) => v) {
    if (typeof arg === 'string' || typeof arg === 'function') {
        const fn = toDynamicFn(arg);
        registerDynamic(item, path, () => valueTransform(fn()));
    } else if (typeof arg === 'number') {
        const targetValue = valueTransform(arg);
        let targets = tweenTargets.get(item);
        if (!targets) {
            targets = new Map();
            tweenTargets.set(item, targets);
        }
        if (duration > 0) {
            if (targets.get(path) === targetValue) return; // same target already commanded — leave the running tween alone
            targets.set(path, targetValue);
            registerTween(item, path, targetValue, duration);
        } else {
            targets.set(path, targetValue);
            unregisterDynamic(item, path);
            setPath(item, path, targetValue);
        }
    }
}

/**
 * Dispatch x/y/z to the right slot in dynamicProps in one call — the 3-axis
 * shape (position/rotation/scale) used by scene-graph worlds like browser_3d.
 *
 * @param {object}   item           the mesh/item
 * @param {string}   propName       e.g. "position" or "rotation"
 * @param {*}        x,y,z          numeric, string expression, ()=>value function, or undefined
 * @param {number}   duration       seconds; applies to numeric args only
 * @param {function} valueTransform converts user value to property unit
 */
function applyTransform(item, propName, x, y, z, duration, valueTransform = (v) => v) {
    for (const [axis, arg] of [['x', x], ['y', y], ['z', z]]) {
        applyDynamic(item, `${propName}.${axis}`, arg, duration, valueTransform);
    }
}

function tickDynamicProps() {
    for (const [item, props] of dynamicProps) {
        for (const [path, fn] of props) {
            try {
                setPath(item, path, fn());
            } catch (e) {
                console.error(`Expression error on ${path}, unregistering:`, e.message);
                unregisterDynamic(item, path);
            }
        }
    }
}

// Support a FUNCTION-ONLY dynamic on a single property (color, text content, ...).
// Unlike size, these args are literal strings when static (a color name, a caption),
// so only a function counts as dynamic: it's evaluated for the initial value and
// re-evaluated per frame, its result passed through `transform` and written to `path`.
// Returns { base } to build with, and register(item) to call once the item exists.
function dynamicProp(arg, path, transform = (v) => v) {
    if (typeof arg !== 'function') {
        return { base: arg, register: () => {} };
    }
    const base = arg();   // initial value for construction
    return {
        base,
        register: (item) => registerDynamic(item, path, () => transform(arg())),
    };
}

// Dynamic color: result run through parseColor (colors.js) and written to `path`
// (fillColor for filled shapes, strokeColor for outlined ones).
// Ex: circle(50, () => TIME.t < 10 ? "lime" : "red")
function dynamicColor(arg, path = 'fillColor') {
    return dynamicProp(arg, path, parseColor);
}

// Once a mutator (currently: scale()) explicitly takes control of a
// (item, path) — e.g. by snapping or tweening it to a fixed value — a
// creator's own reconciled re-invocation must permanently back off from that
// axis, forever (for this item's lifetime), rather than re-asserting its own
// size-driven value. Without this, dynamicSize's guard below (which only
// checks "is *something* currently registered") gets fooled the moment the
// mutator's effect isn't itself an ongoing dynamicProps registration (a snap,
// or a tween that has since completed and self-unregistered) — the very next
// reconciled tick would see nothing registered and reassert its own scaling,
// silently undoing the mutator's call. Keyed by item, not by item+path pairs
// individually, since a WeakMap can't nest cleanly — a small Set per item.
const takenOverPaths = new WeakMap(); // item -> Set<path>

function markTakenOver(item, path) {
    let set = takenOverPaths.get(item);
    if (!set) { set = new Set(); takenOverPaths.set(item, set); }
    set.add(path);
}
function isTakenOver(item, path) {
    const set = takenOverPaths.get(item);
    return !!set && set.has(path);
}

// Support reactive x/y args on 2D creator functions (circle/square/rect/
// ellipse/box/text), the same way dynamicSize's plain-number branch handles
// radius/width/height: a reconciled creator call is simply re-invoked every
// tick with a freshly-evaluated bare expression (see FRP_PHASE2_PLAN.md's
// "bare expression" position note), so re-writing position unconditionally on
// every call is enough to make `text(..., 400 + TIME.t*10, ...)` track TIME.t
// — no wrapper function needed.
// GUARDED the same way scaling is guarded against dynamicSize: once move()
// takes over an axis via markTakenOver, the creator backs off permanently so
// it doesn't fight move()'s explicit repositioning on the very next
// reconciled tick.
function applyCreatorPosition(item, x, y) {
    if (!isTakenOver(item, 'position.x')) item.position.x = x;
    if (!isTakenOver(item, 'position.y')) item.position.y = y;
}

// The "original size" baseline per (item, path) — the value this axis was
// FIRST driven at, used as the denominator for every later scaling-ratio
// computation. Deliberately NOT the same as whatever a creator stores in its
// own display-facing prop (e.g. props.radius) — that field gets overwritten
// every reconciled tick with the *latest* desired value (harmless, since
// nothing re-reads it after construction — see dynamicSize below), which
// would make it useless as a stable denominator to compare against.
const sizeBases = new WeakMap(); // item -> Map<path, baseValue>

// Support dynamic SIZE args on shape creators (radius, width, ...). Effective
// size = base * (current value / base) = current value, at any time — the
// mechanism differs by how `arg` is supplied:
// - plain number: no independent ticking of its own — relies on the RECONCILER
//   re-invoking the creator every tick (a continuous, non-`!` bracket) and
//   simply writes the current ratio directly, right now, each time it's
//   called. This is what makes `circle(50 + TIME.t, "red")` (no wrapper) grow
//   correctly inside a continuous bracket, without needing dynamicSize's own
//   ticking mechanism at all.
// Returns { base } to build the initial geometry with, and register(item) to
// call once the item exists (every tick is fine — see the two guards below).
//
// GUARDED against re-registration: `register`
// is safe to call every tick — from a fresh creation OR a reconciled update of
// the *same* item — because it never recaptures `sizeBases`' stored baseline
// once set, and never re-registers a string/function dynamic that's already
// ticking. Without this, a continuous bracket's creator call being reconciled
// every tick would re-capture the baseline as the *current* value on every
// tick, collapsing the growth ratio to 1 forever.
//
// ALSO GUARDED against fighting a mutator that has taken ownership of this
// axis (`isTakenOver`, above) — e.g. after `scale(c1, 2)`, this backs off
// entirely and never touches that axis again for this item.
//
// @param {*}        arg       number, "t"-expression string, or ()=>value function
// @param {string}   propName  the item's scale property name ("scale" for Three.js, "scaling" for Paper.js)
// @param {string[]} axes      which axes to drive, e.g. ['x','y'] or ['x','y','z']
function dynamicSize(arg, propName, axes) {
    const isDynamic = typeof arg === 'string' || typeof arg === 'function';
    const fn = isDynamic ? toDynamicFn(arg) : null;
    const base = isDynamic ? (fn() || 1) : arg;   // nonzero so the scaling ratio is well-defined

    return {
        base,
        register: (item) => {
            let bases = sizeBases.get(item);
            if (!bases) { bases = new Map(); sizeBases.set(item, bases); }

            for (const axis of axes) {
                const path = `${propName}.${axis}`;
                if (isTakenOver(item, path)) continue; // a mutator (scale()) owns this now — back off permanently

                if (isDynamic) {
                    if (!bases.has(path)) bases.set(path, base); // capture once, at first registration only
                    const existing = dynamicProps.get(item);
                    if (existing && existing.has(path)) continue; // already ticking, correctly-timed — don't recapture
                    const b = bases.get(path);
                    registerDynamic(item, path, () => fn() / b);
                } else {
                    if (!bases.has(path)) bases.set(path, arg || 1); // first time: this number IS the baseline (ratio 1)
                    const b = bases.get(path);
                    unregisterDynamic(item, path); // clear any leftover dynamic (e.g. arg switched from function to number)
                    setPath(item, path, (arg || 0) / b);
                }
            }
        },
    };
}

// The scale an item had when it became audio-reactive, so the pulse multiplies
// onto its own size rather than replacing it. Each world's scale()/audio_reactive()
// read and clear this the same way; shared so the behavior is identical everywhere.
const audioBaseScale = new WeakMap();   // item -> Vector3 | Point

// Expose on the global scope explicitly (rather than relying on bare top-level
// declarations), so editor.html's own inline <script> can reach these
// regardless of exactly how it's structured.
window.TIME = TIME;
window.MIC = MIC;
window.dynamicProps = dynamicProps;
window.registerDynamic = registerDynamic;
window.unregisterDynamic = unregisterDynamic;
window.setPath = setPath;
window.getPath = getPath;
window.toDynamicFn = toDynamicFn;
window.easeOutCubic = easeOutCubic;
window.registerTween = registerTween;
window.applyDynamic = applyDynamic;
window.applyTransform = applyTransform;
window.tickDynamicProps = tickDynamicProps;
window.dynamicProp = dynamicProp;
window.dynamicColor = dynamicColor;
window.dynamicSize = dynamicSize;
window.markTakenOver = markTakenOver;
window.applyCreatorPosition = applyCreatorPosition;
window.audioBaseScale = audioBaseScale;
