/**
 * frp.js — the scene-graph animation engine. Since the FRP-centralization
 * refactor (see listener/FRP_CENTRALIZATION_PLAN.md), this is loaded and runs
 * ONLY in the editor (listener/listen2/editor.html) — the interpreter worlds
 * (browser_2d.html/browser_3d.html) no longer load it at all.
 *
 * Phase 2 (see listener/FRP_PHASE2_PLAN.md) removed the old per-frame ctx-
 * object convention entirely. `TIME` and `MIC` below are persistent, mutable
 * objects — the SAME object every tick, mutated in place by editor.html's
 * tick() — so any closure that captures a reference to them always reads the
 * current value with nothing threaded through as an argument. Every dynamic
 * value below is therefore a **zero-argument** function(), not function(ctx);
 * it reads TIME.t / MIC.audio_level directly wherever it used to read
 * ctx.t / ctx.audioLevel.
 *
 * Every continuous value (position, rotation, scale, opacity, color, ...) is
 * stored as a function() => value, keyed by whatever plain object owns that
 * path — for Phase 1 (and unchanged in Phase 2) that's a world's
 * {id, kind, props} state-store entry's `props`, not a live Paper.js/Three.js
 * object; everything below is generic over "any object with dot-paths". The
 * editor owns the clock and the microphone; once per frame it mutates
 * TIME.t/TIME.dt/MIC.audio_level itself, then calls tickDynamicProps()
 * (advancing every registered dynamic across both worlds' state stores), then
 * posts each world's fully-resolved state down as
 * {type:"applyOps", t, ops, removed} (see editor.html's tick()). A world's
 * applyOps handler just turns that into native objects and renders.
 *
 * A value can be supplied three ways wherever a world's API accepts one:
 * 1. Numeric value (tween from current value to target over 'duration' seconds)
 * 2. String expression (compiled to a function of t; runs continuously) — legacy,
 *    kept for backward compatibility; neither acceptance script uses this anymore.
 * 3. Function () => value (runs continuously; reads TIME/MIC itself)
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

// compile a new expression to a function of t.
function compileExpression(expr) {
    return new Function('t', `return ${expr};`);
}

// Persistent, ambient signal objects — owned here, mutated in place once per
// tick by editor.html's tick() (TIME.t = ...; TIME.dt = ...; MIC.audio_level
// = ...;). Never rebuilt, never passed as an argument: any script closure or
// frp.js internal that holds a reference to these always sees the current
// value. See listener/FRP_PHASE2_PLAN.md section B.
const TIME = { t: 0, dt: 0 };
const MIC = { audio_level: 0 };

// Normalize a continuous-value argument into a zero-argument function() => value.
// - A function is used as-is (expected to be zero-arg and read TIME/MIC itself).
// - A string is compiled as an expression of t and wrapped to read TIME.t.
function toDynamicFn(arg) {
    if (typeof arg === 'function') return arg;
    const compiled = compileExpression(arg);
    return () => compiled(TIME.t);
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

// per-frame: eval every registered dynamic and write the result.
// an error-throwing expression is logged once and unregistered.
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

// Support dynamic SIZE args on shape creators (radius, width, ...). If `arg` is a
// string/function, the shape is built at the expression's current value (the "base")
// and a scaling dynamic is registered on `propName`.`axes` so its size keeps following
// the expression: effective size = base * (expr / base) = expr, at any creation time.
// Returns { base } to build with, and register(item) to call once the item exists
// (a no-op for plain numeric args).
//
// GUARDED against re-registration (PHASE2 plan section E, part 1): `register`
// is safe to call every tick — from a fresh creation OR a reconciled update of
// the *same* item — because it skips (re-)registering any axis that already
// has an active dynamic for this item. Without this guard, a continuous
// bracket's creator call being reconciled every tick would re-capture `base`
// as the *current* value on every tick, collapsing the growth ratio
// (fn() / base) to 1 forever — this is exactly what both acceptance scripts'
// growing-circle line would hit if this guard were missing or wrong.
//
// @param {*}        arg       number, "t"-expression string, or ()=>value function
// @param {string}   propName  the item's scale property name ("scale" for Three.js, "scaling" for Paper.js)
// @param {string[]} axes      which axes to drive, e.g. ['x','y'] or ['x','y','z']
function dynamicSize(arg, propName, axes) {
    if (typeof arg !== 'string' && typeof arg !== 'function') {
        return { base: arg, register: () => {} };
    }
    const fn = toDynamicFn(arg);
    const base = fn() || 1;   // nonzero so the scaling ratio is well-defined
    return {
        base,
        register: (item) => {
            const existing = dynamicProps.get(item);
            for (const axis of axes) {
                const path = `${propName}.${axis}`;
                if (existing && existing.has(path)) continue; // already ticking, correctly-timed — don't recapture base
                registerDynamic(item, path, () => fn() / base);
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
window.compileExpression = compileExpression;
window.toDynamicFn = toDynamicFn;
window.easeOutCubic = easeOutCubic;
window.registerTween = registerTween;
window.applyDynamic = applyDynamic;
window.applyTransform = applyTransform;
window.tickDynamicProps = tickDynamicProps;
window.dynamicProp = dynamicProp;
window.dynamicColor = dynamicColor;
window.dynamicSize = dynamicSize;
window.audioBaseScale = audioBaseScale;
