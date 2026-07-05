/**
 * frp.js — the scene-graph animation engine. Since the FRP-centralization
 * refactor (see listener/FRP_CENTRALIZATION_PLAN.md), this is loaded and runs
 * ONLY in the editor (listener/listen2/editor.html) — the interpreter worlds
 * (browser_2d.html/browser_3d.html) no longer load it at all.
 *
 * Every continuous value (position, rotation, scale, opacity, color, ...) is
 * stored as a function(ctx) => value, keyed by whatever plain object owns that
 * path — for Phase 1 that's a world's {id, kind, props} state-store entry's
 * `props`, not a live Paper.js/Three.js object; everything below is generic
 * over "any object with dot-paths" and needed no changes for that. The editor
 * owns the clock and the microphone; once per frame it calls applyTick(ctx)
 * itself (advancing every registered dynamic across both worlds' state
 * stores), then posts each world's fully-resolved state down as
 * {type:"applyOps", t, ops, removed} (see editor.html's tick()). A world's
 * applyOps handler just turns that into native objects and renders.
 *
 * A value can be supplied three ways wherever a world's API accepts one:
 * 1. Numeric value (tween from current value to target over 'duration' seconds)
 * 2. String expression (compiled to a function of t; runs continuously)
 * 3. Function (ctx) => value (runs continuously)
 */

// item => Map of "prop.subprop" path => function(ctx) => value
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

// The current per-frame signal, cached from the editor's "tick" messages
// (see applyTick). Kept private; read only through buildContext().
let _t = 0;
let _dt = 0;
let _audioLevel = 0;

// Build the per-frame context passed to every dynamic function(ctx).
// Single place to expose more to (ctx) => ... callbacks: add a field here
// and (once applyTick populates it) it's available to every dynamic value.
function buildContext() {
    return {
        t: _t,                   // seconds since the editor's clock started
        dt: _dt,                 // seconds since the previous tick
        audioLevel: _audioLevel, // smoothed mic loudness, 0..1 (pushed from the editor)
    };
}

// Called by a world once per "tick" message from the editor: updates the
// cached signal and advances every registered dynamic.
function applyTick(ctx) {
    _t = ctx.t;
    _dt = ctx.dt;
    _audioLevel = ctx.audioLevel;
    tickDynamicProps();
}

// Normalize a continuous-value argument into a function(ctx) => value.
// - A function is used as-is; it receives the full ctx.
// - A string is compiled as an expression of t and wrapped so it's ctx-driven too.
function toDynamicFn(arg) {
    if (typeof arg === 'function') return arg;
    const compiled = compileExpression(arg);
    return (ctx) => compiled(ctx.t);
}

function easeOutCubic(x) {
    return 1 - Math.pow(1 - x, 3);
}

// register a duration-based tween: animate 'path' from its current value to
// 'targetValue' over 'duration' seconds, then self-unregister.
function registerTween(item, path, targetValue, duration) {
    const fromValue = getPath(item, path);
    const startT = _t;
    const endT = startT + duration;
    registerDynamic(item, path, (ctx) => {
        const now = ctx.t;
        if (now >= endT) {
            unregisterDynamic(item, path);
            return targetValue;
        }
        const progress = (now - startT) / duration;
        return fromValue + (targetValue - fromValue) * easeOutCubic(progress);
    });
}

// Apply one value (number | string expr | (ctx)=>value) to one property path.
// Numbers snap (duration 0) or tween; strings/functions run continuously.
function applyDynamic(item, path, arg, duration, valueTransform = (v) => v) {
    if (typeof arg === 'string' || typeof arg === 'function') {
        const fn = toDynamicFn(arg);
        registerDynamic(item, path, (ctx) => valueTransform(fn(ctx)));
    } else if (typeof arg === 'number') {
        unregisterDynamic(item, path);
        const targetValue = valueTransform(arg);
        if (duration > 0) {
            registerTween(item, path, targetValue, duration);
        } else {
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
 * @param {*}        x,y,z          numeric, string expression, (ctx)=>value function, or undefined
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
    const ctx = buildContext();
    for (const [item, props] of dynamicProps) {
        for (const [path, fn] of props) {
            try {
                setPath(item, path, fn(ctx));
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
    const base = arg(buildContext());   // initial value for construction
    return {
        base,
        register: (item) => registerDynamic(item, path, (ctx) => transform(arg(ctx))),
    };
}

// Dynamic color: result run through parseColor (colors.js) and written to `path`
// (fillColor for filled shapes, strokeColor for outlined ones).
// Ex: circle(50, (c) => c.t < 10 ? "lime" : "red")
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
// @param {*}        arg       number, "t"-expression string, or (ctx)=>value function
// @param {string}   propName  the item's scale property name ("scale" for Three.js, "scaling" for Paper.js)
// @param {string[]} axes      which axes to drive, e.g. ['x','y'] or ['x','y','z']
function dynamicSize(arg, propName, axes) {
    if (typeof arg !== 'string' && typeof arg !== 'function') {
        return { base: arg, register: () => {} };
    }
    const fn = toDynamicFn(arg);
    const base = fn(buildContext()) || 1;   // nonzero so the scaling ratio is well-defined
    return {
        base,
        register: (item) => {
            for (const axis of axes) {
                registerDynamic(item, `${propName}.${axis}`, (ctx) => fn(ctx) / base);
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
window.dynamicProps = dynamicProps;
window.registerDynamic = registerDynamic;
window.unregisterDynamic = unregisterDynamic;
window.setPath = setPath;
window.getPath = getPath;
window.compileExpression = compileExpression;
window.buildContext = buildContext;
window.applyTick = applyTick;
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
