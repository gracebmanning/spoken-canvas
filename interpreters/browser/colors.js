/**
 * colors.js — shared color palette for the browser interpreters.
 *
 * Keep this list in sync with the TouchDesigner interpreter's COLOR_MAP
 * (same names, same hex codes) so each color word looks identical on every target.
 */
const COLOR_MAP = {
    // Reds / Oranges
    red: "#FB2C36",
    orange: "#FF6900",
    amber: "#FD9A00",
    yellow: "#EFB100",
    // Greens
    lime: "#7CCF00",
    green: "#00C950",
    emerald: "#00BC7D",
    teal: "#00BBA7",
    // Blues
    cyan: "#00B8DB",
    blue: "#2B7FFF",
    indigo: "#615FFF",
    violet: "#8E51FF",
    // Pinks / Purples
    purple: "#AD46FF",
    magenta: "#E12AFB",
    pink: "#FDA5D5",
    mauve: "#E0B0CF",
    // Neutrals
    white: "#FFFFFF",
    gray: "#6A7282",
    black: "#000000",
    brown: "#733E0A",
};

/**
 * Resolve a color word or hex string to a hex value.
 * - Named colors (case-insensitive) map to their hex code.
 * - Anything else (e.g. "#FF8800") is passed through unchanged, so custom
 *   colors still work.
 * Quotes are stripped before lookup so eval'd commands like circle(50, "red")
 * resolve whether or not the argument arrives quoted.
 */
function parseColor(colorStr) {
    const key = String(colorStr).toLowerCase().replace(/['"]/g, "");
    return COLOR_MAP[key] || colorStr;
}

/*
 * Expose on the global scope for the interpreters and for eval'd commands.
 * (Top-level const/function are reachable by name within the page, but we also
 * attach to window so access is explicit and robust regardless of script type.)
 */
window.COLOR_MAP = COLOR_MAP;
window.parseColor = parseColor;
