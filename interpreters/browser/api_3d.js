/**
 * api_3d.js — the browser_3d (Three.js-shaped) script verb API.
 *
 * Loaded by the editor (listener/listen2/editor.html) alongside frp.js/
 * colors.js, BEFORE the editor's own inline script runs. makeWorld3DApi()
 * itself is only ever CALLED from that inline script (building worldApis),
 * by which point the editor's shared per-world state engine — reconcileCreate/
 * resolveHandle/removeFromWorld/clearWorld, plus frp.js's applyTransform/
 * audioBaseScale/registerTween/unregisterDynamic/registerDynamic/toDynamicFn
 * and colors.js's parseColor — already exists on the shared global scope, so
 * everything referenced inside can resolve normally despite living in a
 * separate file loaded earlier.
 */

// Resolve a color to hex {r,g,b} in 0..1 (THREE.Color-shaped) without
// depending on THREE.js, which the editor never loads. Only used by the 3D
// world's `color()` mutator, which needs per-channel numbers to support
// tweening (a plain props object can't hold a live THREE.Color that
// auto-parses hex strings the way the old per-iframe code relied on).
function hexToRgb01(hex) {
  const s = String(hex).replace('#', '');
  const full = s.length === 3 ? s.split('').map((c) => c + c).join('') : s.padStart(6, '0');
  const num = parseInt(full, 16) || 0;
  return {
    r: ((num >> 16) & 0xff) / 255,
    g: ((num >> 8) & 0xff) / 255,
    b: (num & 0xff) / 255,
  };
}

// ---- 3D verb functions (Three.js-shaped props) -----------------------
// 3D creators have no dynamic-size/color support today, matching the old
// per-iframe code (not added — out of scope here too): geometry and the
// initial color are fixed numbers/strings resolved once, at creation.
function makeWorld3DApi(world) {
  // Shared "generic Item lifecycle" defaults for a brand-new 3D entity —
  // position/rotation/scale/opacity/transparent/noiseIntensity are owned
  // from then on by move()/rotate()/scale()/opacity()/audio_reactive()/
  // noise(), so a reconciled *update* call (see reconcileCreate above)
  // must NOT reset them — only a fresh creation sets them. `color` is
  // included here too (not in the "recomputed every reconcile" set below)
  // because 3D has a dedicated color() verb, same reasoning as 2D's
  // position: re-asserting the creator's flat construction color on every
  // reconciled tick would fight a live color()-tween exactly the way
  // resetting position would fight move() (see PHASE2 plan section D/E
  // trace in the implementation notes).
  function freshMeshDefaults(x, y, color) {
    return {
      position: { x, y, z: 0 },
      rotation: { x: 0, y: 0, z: 0 },
      scale: { x: 1, y: 1, z: 1 },
      color: hexToRgb01(parseColor(color)),
      opacity: 1,
      transparent: false,
      noiseIntensity: 0,
    };
  }

  /** Create a box mesh and add it to the scene. */
  function cube(sizex = 1.0, sizey, sizez, color = "white", x = 0, y = 0) {
    if (sizey === undefined) sizey = sizex;
    if (sizez === undefined) sizez = sizex;
    return reconcileCreate(world, 'cube', cube, (props) => {
      if (!props) props = freshMeshDefaults(x, y, color);
      props.size = { x: sizex, y: sizey, z: sizez };
      return props;
    });
  }

  /** Create a sphere or ellipsoid. A string in any size slot is the color. */
  function sphere(radx = 0.5, rady, radz, color = "white", x = 0, y = 0) {
    if (rady === undefined) rady = radx;
    if (radz === undefined) radz = radx;
    return reconcileCreate(world, 'sphere', sphere, (props) => {
      if (!props) props = freshMeshDefaults(x, y, color);
      props.radius = { x: radx, y: rady, z: radz };
      return props;
    });
  }

  /** Create a torus (donut shape). String shorthand: torus(0.6, "orange"). */
  function torus(radx = 0.5, rady = 0.25, color = "white", x = 0, y = 0) {
    return reconcileCreate(world, 'torus', torus, (props) => {
      if (!props) props = freshMeshDefaults(x, y, color);
      props.radius = { outer: radx, tube: rady };
      return props;
    });
  }

  /** Create a tube: cylinder, cone, or truncated cone (frustum). */
  function tube(rad1 = 0.5, rad2, height = 0.5, color = "white", x = 0, y = 0) {
    if (rad2 === undefined) rad2 = rad1; // cylinder by default
    return reconcileCreate(world, 'tube', tube, (props) => {
      if (!props) props = freshMeshDefaults(x, y, color);
      props.radius = { top: rad1, bottom: rad2 };
      props.height = height;
      return props;
    });
  }

  /**
   * Create a point cloud (scattered Gaussian points). Like vertex noise,
   * the actual per-point scatter is a native, largish data blob generated
   * once, locally, by the 3D world from these small scalar props — see
   * browser_3d.html's constructNative('cloud', ...).
   */
  function cloud(quantity = 1.0, spread = 1.0, color = "white", shape = "circle", x = 0, y = 0) {
    return reconcileCreate(world, 'cloud', cloud, (props) => {
      if (!props) props = freshMeshDefaults(x, y, color);
      props.quantity = quantity;
      props.spread = spread;
      props.pointShape = shape;
      return props;
    });
  }

  /** Move a shape. Each axis arg: number (snap/tween), "t"-expression, or ()=>value. */
  function move(handle, x = 0.0, y = 0.0, z = 0.0, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    applyTransform(entry.props, 'position', x, y, z, duration);
  }

  /**
   * Rotate a shape. Angles are in degrees, converted to radians here (the
   * editor), exactly where the old per-iframe code used to convert them —
   * the world receives already-radian values, matching Three's native unit.
   */
  function rotate(handle, rx = 0.0, ry = 0.0, rz = 0.0, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    const degToRad = (deg) => deg * Math.PI / 180;
    applyTransform(entry.props, 'rotation', rx, ry, rz, duration, degToRad);
  }

  /** Scale a shape. sy/sz default to sx. scale(b1) with no other args resets to (1,1,1). */
  function scale(handle, sx = 1.0, sy, sz, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    if (sy === undefined) sy = sx;
    if (sz === undefined) sz = sx;
    audioBaseScale.delete(entry.props); // take over scale control and drop audio reactivity
    applyTransform(entry.props, 'scale', sx, sy, sz, duration);
  }

  /**
   * Give a shape organic movement by drifting its vertices with a noise
   * field. This just sets a single scalar prop — the actual per-vertex
   * drift stays local to the 3D world (see updateVertexNoise there).
   * noise(shape, 0) stops and snaps back to the original positions.
   */
  function noise(handle, intensity = 0.5) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    entry.props.noiseIntensity = Math.max(0, Math.min(1, intensity));
  }

  /** Recolor a shape. */
  function color(handle, colorValue, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    const target = hexToRgb01(parseColor(colorValue));
    unregisterDynamic(entry.props, 'color.r');
    unregisterDynamic(entry.props, 'color.g');
    unregisterDynamic(entry.props, 'color.b');
    if (duration > 0) {
      registerTween(entry.props, 'color.r', target.r, duration);
      registerTween(entry.props, 'color.g', target.g, duration);
      registerTween(entry.props, 'color.b', target.b, duration);
    } else {
      entry.props.color = target;
    }
  }

  /** Set a shape's opacity (0 = invisible, 1 = opaque). */
  function opacity(handle, value = 1.0, duration = 0) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;

    if (typeof value === 'string' || typeof value === 'function') {
      // expression/function -> per-frame opacity; can dip below 1 at any
      // time, so the world must keep blending on regardless of duration.
      entry.props.transparent = true;
      registerDynamic(entry.props, 'opacity', toDynamicFn(value));
      return;
    }

    // numeric: stop any running fade/expression first.
    unregisterDynamic(entry.props, 'opacity');
    if (duration > 0) {
      entry.props.transparent = true; // dips below 1 mid-fade
      registerTween(entry.props, 'opacity', value, duration);
    } else {
      entry.props.opacity = value;
      entry.props.transparent = value < 1; // only blend when not fully opaque
    }
  }

  function remove(handle) {
    const entry = resolveHandle(world, handle);
    if (!entry) return;
    removeFromWorld(world, handle.__id);
  }

  function clear() {
    clearWorld(world);
  }

  return { cube, sphere, torus, tube, cloud, move, rotate, scale,  noise, color, opacity, remove, clear };
}

// Expose on the global scope explicitly (rather than relying on bare
// top-level declarations), matching frp.js/colors.js's convention.
window.hexToRgb01 = hexToRgb01;
window.makeWorld3DApi = makeWorld3DApi;
