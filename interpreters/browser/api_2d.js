/**
 * api_2d.js — the browser_2d (Paper.js-shaped) script verb API.
 *
 * Loaded by the editor (listener/listen2/editor.html) alongside frp.js/
 * colors.js, BEFORE the editor's own inline script runs. makeWorld2DApi()
 * itself is only ever CALLED from that inline script (building worldApis),
 * by which point the editor's shared per-world state engine — reconcileCreate/
 * resolveHandle/removeFromWorld/clearWorld/markTakenOver, plus frp.js's
 * dynamicSize/dynamicColor/dynamicProp/applyDynamic/audioBaseScale and
 * colors.js's parseColor — already exists on the shared global scope, so
 * everything referenced inside can resolve normally despite living in a
 * separate file loaded earlier.
 */

// Paper.js's canvas is a fixed 1920x1080 (see the .frame CSS / browser_2d's
// canvas.width/height); the editor doesn't load Paper.js, so it can't ask
// `view.center` for the default center the way the old creators did —
// hardcode the equivalent instead.
const DEFAULT_CENTER_2D = { x: 960, y: 540 };

// ---- 2D verb functions (Paper.js-shaped props) -----------------------
// Argument resolution (number | "t"-expression string | ()=>value) is
// unchanged from before — dynamicSize/dynamicColor/dynamicProp/applyDynamic
// (frp.js) already normalize that generically; only what they're pointed
// at changes (a plain props object's paths instead of a Paper.js item).
function makeWorld2DApi(world) {
  // Any size arg (radius/width/height) may be a number, a "t"-expression
  // string, or a ()=>value function; a dynamic one makes the shape grow/
  // shrink over time. Ex: circle(() => 50 + TIME.t, "red")
  function circle(radius, color, x = DEFAULT_CENTER_2D.x, y = DEFAULT_CENTER_2D.y) {
    return reconcileCreate(world, 'circle', circle, (props) => {
      if (!props) props = { position: { x, y }, scaling: { x: 1, y: 1 }, rotation: 0, opacity: 1 };
      applyCreatorPosition(props, x, y);
      const r = dynamicSize(radius, 'scaling', ['x', 'y']);
      const col = dynamicColor(color);
      props.radius = r.base;
      props.fillColor = parseColor(col.base);
      r.register(props);
      col.register(props);
      return props;
    });
  }

  function square(size, color, x = DEFAULT_CENTER_2D.x, y = DEFAULT_CENTER_2D.y) {
    return reconcileCreate(world, 'square', square, (props) => {
      if (!props) props = { position: { x, y }, scaling: { x: 1, y: 1 }, rotation: 0, opacity: 1 };
      applyCreatorPosition(props, x, y);
      const s = dynamicSize(size, 'scaling', ['x', 'y']);
      const col = dynamicColor(color);
      props.size = { width: s.base, height: s.base };
      props.fillColor = parseColor(col.base);
      s.register(props);
      col.register(props);
      return props;
    });
  }

  function rect(width, height, color, x = DEFAULT_CENTER_2D.x, y = DEFAULT_CENTER_2D.y) {
    return reconcileCreate(world, 'rect', rect, (props) => {
      if (!props) props = { position: { x, y }, scaling: { x: 1, y: 1 }, rotation: 0, opacity: 1 };
      applyCreatorPosition(props, x, y);
      const w = dynamicSize(width, 'scaling', ['x']);
      const h = dynamicSize(height, 'scaling', ['y']);
      const col = dynamicColor(color);
      props.size = { width: w.base, height: h.base };
      props.fillColor = parseColor(col.base);
      w.register(props);
      h.register(props);
      col.register(props);
      return props;
    });
  }

  function ellipse(width, height, color, x = DEFAULT_CENTER_2D.x, y = DEFAULT_CENTER_2D.y) {
    return reconcileCreate(world, 'ellipse', ellipse, (props) => {
      if (!props) props = { position: { x, y }, scaling: { x: 1, y: 1 }, rotation: 0, opacity: 1 };
      applyCreatorPosition(props, x, y);
      const w = dynamicSize(width, 'scaling', ['x']);
      const h = dynamicSize(height, 'scaling', ['y']);
      const col = dynamicColor(color);
      props.size = { width: w.base, height: h.base };
      props.fillColor = parseColor(col.base);
      w.register(props);
      h.register(props);
      col.register(props);
      return props;
    });
  }

  // Create an arrow from point A to point B. No dynamic size/color support
  // in the old code either (only color could be dynamic) — preserved as-is.
  function arrow(fromX, fromY, toX, toY, color = 'black', thickness = 3) {
    return reconcileCreate(world, 'arrow', arrow, (props) => {
      const col = dynamicColor(color, 'strokeColor');

      const dx = toX - fromX;
      const dy = toY - fromY;
      const angle = Math.atan2(dy, dx);
      const arrowLength = 15;
      const arrowAngle = Math.PI / 6; // 30 degrees

      const lines = [
        { from: { x: fromX, y: fromY }, to: { x: toX, y: toY } },
        {
          from: { x: toX, y: toY },
          to: {
            x: toX - arrowLength * Math.cos(angle - arrowAngle),
            y: toY - arrowLength * Math.sin(angle - arrowAngle),
          },
        },
        {
          from: { x: toX, y: toY },
          to: {
            x: toX - arrowLength * Math.cos(angle + arrowAngle),
            y: toY - arrowLength * Math.sin(angle + arrowAngle),
          },
        },
      ];

      if (!props) {
        // Arrow has no natural single "position" the way a centered shape
        // does; the from/to midpoint is a reasonable stand-in so move()/
        // rotate()/scale() still work generically (a few-pixel recentering
        // vs. the group's raw bounding box, which nothing depends on today).
        props = {
          position: { x: (fromX + toX) / 2, y: (fromY + toY) / 2 },
          rotation: 0,
          scaling: { x: 1, y: 1 },
          opacity: 1,
        };
      }
      props.lines = lines;
      props.strokeWidth = thickness;
      props.strokeColor = parseColor(col.base);
      col.register(props);
      return props;
    });
  }

  function line(fromX, fromY, toX, toY, color = 'white', thickness = 3) {
    return reconcileCreate(world, 'line', line, (props) => {
      const col = dynamicColor(color, 'strokeColor');
      if (!props) {
        props = {
          position: { x: (fromX + toX) / 2, y: (fromY + toY) / 2 },
          rotation: 0,
          scaling: { x: 1, y: 1 },
          opacity: 1,
        };
      }
      props.from = { x: fromX, y: fromY };
      props.to = { x: toX, y: toY };
      props.strokeWidth = thickness;
      props.strokeColor = parseColor(col.base);
      col.register(props);
      return props;
    });
  }

  // content may be a literal (number/string) or a ()=>value function for
  // live text. align is "left", "center", or "right", relative to (x, y).
  // Ex: text(() => "Time: " + TIME.t.toFixed(1), 400, 270, 100, "cyan", "left")
  function text(content, x = DEFAULT_CENTER_2D.x, y = DEFAULT_CENTER_2D.y, size = 24, color = 'white', align = 'center') {
    return reconcileCreate(world, 'text', text, (props) => {
      if (!props) props = { position: { x, y }, rotation: 0, scaling: { x: 1, y: 1 }, opacity: 1 };
      applyCreatorPosition(props, x, y);
      const txt = dynamicProp(content, 'content', String);
      const col = dynamicColor(color);
      props.content = String(txt.base);
      props.fontSize = size;
      props.align = align;
      props.fillColor = parseColor(col.base);
      txt.register(props);
      col.register(props);
      return props;
    });
  }

  // Create a box (rectangle with border, no fill) - useful for diagrams
  function box(width, height, color = 'white', x = DEFAULT_CENTER_2D.x, y = DEFAULT_CENTER_2D.y, borderWidth = 2) {
    return reconcileCreate(world, 'box', box, (props) => {
      if (!props) props = { position: { x, y }, scaling: { x: 1, y: 1 }, rotation: 0, opacity: 1 };
      applyCreatorPosition(props, x, y);
      const w = dynamicSize(width, 'scaling', ['x']);
      const h = dynamicSize(height, 'scaling', ['y']);
      const col = dynamicColor(color, 'strokeColor');
      props.size = { width: w.base, height: h.base };
      props.strokeColor = parseColor(col.base);
      props.strokeWidth = borderWidth;
      props.fillColor = null;
      w.register(props);
      h.register(props);
      col.register(props);
      return props;
    });
  }

  /**
   * Move an item. Each of x/y can be a number (snap or tween), a "t"-expression
   * string, or a ()=>value function. Mixed args allowed.
   * Ex: move(c, "center.x + 200 * Math.sin(t)", center.y)
   */
  function move(handle, x = DEFAULT_CENTER_2D.x, y = DEFAULT_CENTER_2D.y, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    // Take over from any creator-driven position (applyCreatorPosition) —
    // without this, a continuously-reconciled circle/square/.../text
    // creation call would silently reassert its own x/y the very next
    // tick, undoing this call (see frp.js's applyCreatorPosition/isTakenOver).
    markTakenOver(entry.props, 'position.x');
    markTakenOver(entry.props, 'position.y');
    applyDynamic(entry.props, 'position.x', x, duration);
    applyDynamic(entry.props, 'position.y', y, duration);
  }

  /**
   * Rotate an item to an ABSOLUTE angle in degrees (matches browser_3d).
   * Number => snap/tween; string/function => continuous, e.g. "t * 60" spins 60 deg/sec.
   */
  function rotate(handle, degrees = 0, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    applyDynamic(entry.props, 'rotation', degrees, duration);
  }

  /**
   * Scale an item by an ABSOLUTE factor (1 = original size). sy defaults to sx.
   * Number => snap/tween; string/function => continuous pulse.
   */
  function scale(handle, sx = 1.0, sy, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    if (sy === undefined) sy = sx;
    audioBaseScale.delete(entry.props);   // take over scale control, drop audio reactivity
    // Also take over from any creator-driven size dynamic (dynamicSize) —
    // without this, a continuously-reconciled circle/square/rect/ellipse/box
    // creation call would silently reassert its own scaling the very next
    // tick, undoing this call (see frp.js's dynamicSize/isTakenOver).
    markTakenOver(entry.props, 'scaling.x');
    markTakenOver(entry.props, 'scaling.y');
    applyDynamic(entry.props, 'scaling.x', sx, duration);
    applyDynamic(entry.props, 'scaling.y', sy, duration);
  }

  /**
   * Set an item's opacity (0 = invisible, 1 = opaque).
   */
  function fade(handle, value = 1.0, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    applyDynamic(entry.props, 'opacity', value, duration);
  }

  function remove(handle) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    removeFromWorld(world, handle.__id);
  }

  function clear() {
    clearWorld(world);
  }

  return { circle, square, rect, ellipse, arrow, line, text, box, move, rotate, scale, fade, opacity: fade, remove, clear };
}

// Expose on the global scope explicitly (rather than relying on bare
// top-level declarations), matching frp.js/colors.js's convention.
window.DEFAULT_CENTER_2D = DEFAULT_CENTER_2D;
window.makeWorld2DApi = makeWorld2DApi;
