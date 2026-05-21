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
 * Open a WebSocket to the relay, self-filter by target, and route messages to
 * callbacks. Reconnects automatically up to maxReconnectAttempts.
 *
 * @param {object}   options
 * @param {string}   options.target                 this interpreter's target ("browser_2d", ...)
 * @param {string}   [options.url]                   relay URL
 * @param {function} [options.onExecute]             called with the code string for command:"execute"
 * @param {function} [options.onPosition]            called with the full message for command:"update_position"
 * @param {function} [options.onStatus]              called with human-readable status strings
 * @param {number}   [options.maxReconnectAttempts]
 * @param {number}   [options.reconnectDelayMs]
 */
function connectInterpreter({
    target,
    url = "ws://127.0.0.1:8000/ws",
    onExecute,
    onPosition,
    onStatus = () => {},
    maxReconnectAttempts = 5,
    reconnectDelayMs = 2000,
}) {
    let ws;
    let reconnectAttempts = 0;

    function connect() {
        try {
            onStatus("Connecting to: " + url);
            ws = new WebSocket(url);

            ws.onopen = () => {
                reconnectAttempts = 0;
                onStatus("Connected! Waiting for commands...");
                console.log("WebSocket connected as", target);
            };

            ws.onmessage = (event) => {
                let data;
                try {
                    data = JSON.parse(event.data);
                } catch (e) {
                    onStatus("Parse error: " + e.message);
                    console.error("Parse error:", e);
                    return;
                }

                // Self-filter: ignore messages addressed to a different interpreter.
                // A message with no target is accepted by everyone (original behavior).
                if (data.target && data.target !== target) return;

                if (data.command === "execute") {
                    if (onExecute) onExecute(data.code);
                } else if (data.command === "update_position") {
                    if (onPosition) onPosition(data);
                }
            };

            ws.onerror = (error) => {
                onStatus("WebSocket error");
                console.error("WebSocket error:", error);
            };

            ws.onclose = () => {
                onStatus("Disconnected");
                console.log("WebSocket closed");
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    onStatus("Reconnecting... attempt " + reconnectAttempts);
                    setTimeout(connect, reconnectDelayMs);
                }
            };
        } catch (e) {
            onStatus("Error creating WebSocket: " + e.message);
        }
    }

    connect();
}

// Expose on the global scope for the interpreter scripts.
window.globalizeDeclarations = globalizeDeclarations;
window.executeCommand = executeCommand;
window.connectInterpreter = connectInterpreter;
