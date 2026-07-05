/**
 * interpreter_core.js — shared plumbing for the browser interpreter worlds
 * (browser_2d.html / browser_3d.html).
 *
 * Since the FRP-centralization refactor, worlds no longer eval script code
 * and no longer run their own animation clock — the editor (listener/listen2/
 * editor.html) owns the verb functions, the FRP engine (frp.js), and a plain
 * {id, kind, props} state store per world. Once per frame the editor posts the
 * *full current state* of every live object for a world:
 *
 *   {type: "applyOps", t, ops: [{id, kind, props}, ...], removed: [id, ...]}
 *
 * A world's only job is to turn that into native Paper.js/Three.js objects —
 * it never sees script text and never calls eval. This file is now just the
 * tiny shared message listener both worlds use for that.
 */
function connectToEditor({ onApplyOps } = {}) {
    window.addEventListener("message", (event) => {
        const msg = event.data;
        if (!msg || typeof msg !== "object") return;
        if (msg.type === "applyOps" && onApplyOps) onApplyOps(msg);
    });
}

// Expose on the global scope for the interpreter worlds.
window.connectToEditor = connectToEditor;
