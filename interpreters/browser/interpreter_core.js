/**
 * interpreter_core.js — shared plumbing for the browser interpreters.
 */

/**
 * Promote top-of-statement `let`/`const`/`var` declarations to `window.*` so a
 * variable created in one command survives into later commands. (A bare `let`
 * inside an eval() is scoped to that single eval call and would otherwise
 * vanish before the next command runs.)
 *
 * The match is anchored to a statement boundary (start of string, newline, or
 * ';'), which keeps it from rewriting text that only *looks* like a
 * declaration:
 *   text("let x = 5")      ->  unchanged   (inside a string literal)
 *   for (let i = 0; ...)   ->  unchanged   (loop counter stays local)
 *   let b1 = cube(...)     ->  window.b1 = cube(...)   (real handle, promoted)
 */
function globalizeDeclarations(code) {
    return code.replace(/(^|\n|;)(\s*)(?:let|const|var)\s+(\w+)\s*=/g, "$1$2window.$3 =");
}

/**
 * Execute a command string in the global scope.
 *
 * @param {string}   code                  the command to run
 * @param {object}   [hooks]
 * @param {function} [hooks.afterExecute]   run after a successful eval (e.g. force a redraw)
 * @param {function} [hooks.onError]        called with the Error if execution throws
 */
function executeCommand(code, { afterExecute, onError } = {}) {
    try {
        // Indirect eval -> always runs in the global scope, so commands can see the
        // interpreter's globals (circle, cube, parseColor, ...) regardless of which
        // file this function happens to live in.
        (0, eval)(globalizeDeclarations(code));
        if (afterExecute) afterExecute();
    } catch (e) {
        console.error("Execution error:", e);
        if (onError) onError(e);
    }
}

/**
 * Listen for messages from the top-level editor page (same-origin parent, via
 * postMessage — no relay process involved):
 * - {type: "execute", code}   a script command to eval (see executeCommand)
 * - {type: "tick", ctx}       the per-frame signal {t, dt, audioLevel}; see frp.js's applyTick
 *
 * @param {object}   options
 * @param {function} [options.onExecute]   called with the code string
 * @param {function} [options.onTick]      called with the ctx object
 */
function connectToEditor({ onExecute, onTick } = {}) {
    window.addEventListener("message", (event) => {
        const msg = event.data;
        if (!msg || typeof msg !== "object") return;
        if (msg.type === "execute" && onExecute) onExecute(msg.code);
        else if (msg.type === "tick" && onTick) onTick(msg.ctx);
    });
}

// Expose on the global scope for the interpreter scripts.
window.globalizeDeclarations = globalizeDeclarations;
window.executeCommand = executeCommand;
window.connectToEditor = connectToEditor;
