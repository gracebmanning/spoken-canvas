"""
td_api.py
=========
TouchDesigner API for handling execute commands from the listener.
Called by the WebSocket callback DAT via mod(op("td_api")).handle(data).

Commands are executed via Python's exec() in a persistent namespace that
contains all available TD API functions. This allows arbitrary Python
expressions — including variable assignment, lambdas, and multi-step logic —
as long as they are valid Python after JS declaration keywords are stripped.

JS keywords stripped before exec:
    let, const, var

Stacking behavior:
    - Each new shape Base COMP is inserted at index 0 in the shapes_composite
      (top layer), matching the browser's painter's algorithm
    - clear() destroys all tracked shapes and resets the composite
"""
import td   # type: ignore
import re

COLOR_MAP = {
    # Reds / Oranges
    'red':     [1.0,   0.0,   0.0],
    'orange':  [1.0,   0.647, 0.0],
    'amber':   [1.0,   0.749, 0.0],
    'yellow':  [1.0,   1.0,   0.0],
    # Greens
    'lime':    [0.749, 1.0,   0.0],
    'green':   [0.0,   1.0,   0.0],
    'emerald': [0.314, 0.784, 0.471],
    'teal':    [0.0,   0.502, 0.502],
    # Blues
    'cyan':    [0.0,   1.0,   1.0],
    'blue':    [0.0,   0.0,   1.0],
    'indigo':  [0.294, 0.0,   0.510],
    'violet':  [0.933, 0.510, 0.933],
    # Pinks / Purples
    'purple':  [0.502, 0.0,   0.502],
    'magenta': [1.0,   0.0,   1.0],
    'pink':    [1.0,   0.753, 0.796],
    'mauve':   [0.878, 0.690, 0.812],
    # Neutrals
    'white':   [1.0,   1.0,   1.0],
    'gray':    [0.502, 0.502, 0.502],
    'black':   [0.0,   0.0,   0.0],
    'brown':   [0.545, 0.271, 0.075],
}


def parse_color(color_val):
    """
    Convert a color name or hex string to a normalized RGB list.

    Args:
        color_val: A string like "red", "blue", or "#FF0000"

    Returns:
        List of three floats [r, g, b] in range [0.0, 1.0]

    Raises:
        ValueError: If the color string is not recognized
    """
    normalized = str(color_val).strip().strip('"\'').lower()

    if normalized in COLOR_MAP:
        return COLOR_MAP[normalized]

    # Try CSS hex string e.g. "#FF0000" or "FF0000"
    hex_str = normalized.lstrip('#')
    if len(hex_str) == 6:
        try:
            r = int(hex_str[0:2], 16) / 255.0
            g = int(hex_str[2:4], 16) / 255.0
            b = int(hex_str[4:6], 16) / 255.0
            return [round(r, 4), round(g, 4), round(b, 4)]
        except ValueError:
            pass

    raise ValueError(
        f"Unknown color: '{color_val}'. "
        f"Use a named color {list(COLOR_MAP.keys())} or a CSS hex string."
    )


# ============================================================
# NAMESPACE MANAGEMENT
# The execution namespace persists across commands so that variables
# assigned in one command (e.g. c1 = circle(...)) are accessible in
# later commands (e.g. move(c1, ...)). The namespace is kept in
# parent storage between calls.
# ============================================================

def _get_namespace():
    """
    Retrieve the persistent execution namespace from parent storage
    and repopulate it with current API functions.
    """
    parent = me.parent()    # type: ignore
    namespace = parent.fetch('td_namespace', {})

    # Always repopulate API functions in case the DAT was reloaded
    namespace.update({
        'box':   box,
        'sphere': sphere,
        'torus':  torus,
        'tube':   tube,
        'move': move,
        'rotate': rotate,
        'scale': scale,
        'audio_reactive': audio_reactive,
        'color': color,
        'opacity': opacity,
        'remove': remove,
        'clear': clear,
    })

    return namespace


def _save_namespace(namespace):
    """
    Save the execution namespace back to parent storage.
    Strips API function references before saving — they are re-injected
    on each call to _get_namespace().
    """
    parent = me.parent()    # type: ignore
    api_keys = {'box', 'sphere', 'torus', 'tube', 'move', 'rotate',
                'scale', 'audio_reactive', 'color', 'opacity', 'remove', 'clear'}
    saveable = {k: v for k, v in namespace.items()
                if k not in api_keys and not k.startswith('__')}
    parent.store('td_namespace', saveable)

# ============================================================
# ENTRY POINT
# ============================================================


def handle(data):
    """
    Entry point called by the WebSocket callback DAT for execute commands.

    Args:
        data: Parsed JSON dict, e.g.
              {"target": "td", "command": "execute", "code": "let c1 = box('white')"}
    """
    code = data.get("code", "").strip()
    if not code:
        print("TD API: received empty code string")
        return

    # Strip JavaScript declaration keywords — not valid Python
    code = re.sub(r'\b(let|const|var)\s+', '', code)

    print(f"TD API executing: {code}")

    namespace = _get_namespace()

    try:
        exec(code, namespace)
        _save_namespace(namespace)
    except Exception as e:
        print(f"TD API execution error: {e}")
        import traceback
        traceback.print_exc()

# ============================================================
# HELPERS
# ============================================================


def _auto_name(prefix):
    """Generate a unique operator name when none was provided."""
    parent = me.parent()    # type: ignore
    shapes = parent.fetch('td_shapes', [])
    count = sum(1 for s in shapes if s.startswith(prefix))
    return f"{prefix}_{count + 1}"


def _rebuild_composite():
    """
    Reconnect all tracked shape Base COMPs to shapes_composite.
    Index 0 = top layer (newest), matching the browser's stacking behavior.
    """
    parent = me.parent()    # type: ignore
    shapes_container = parent.op('shapes')
    comp = shapes_container.op('shapes_composite')
    if not comp:
        print("TD API: shapes_composite not found")
        return

    shapes = parent.fetch('td_shapes', [])

    for connector in list(comp.inputConnectors):
        connector.disconnect()

    for i, name in enumerate(shapes):
        base = shapes_container.op(name)
        if base:
            base.outputConnectors[0].connect(comp.inputConnectors[i])


def _create_sop(op_type, parent_comp):
    """
    Build the standard SOP → Transform → Geometry COMP → Render TOP → Out TOP
    chain inside a Base COMP. The shared camera and light live one level up
    in shapes_container and are referenced by relative path.

    Args:
        op_type:     A TD SOP type (e.g. td.boxSOP, td.sphereSOP)
        parent_comp: The Base COMP to build inside

    Returns:
        The Out TOP, so callers can wire it into the composite
    """
    sop = parent_comp.create(op_type)
    sop.viewer = True
    sop.nodeX = -400
    sop.nodeY = 0

    transform = parent_comp.create(td.transformSOP)
    transform.viewer = True
    transform.nodeX = -200
    transform.nodeY = 0
    transform.inputConnectors[0].connect(sop.outputConnectors[0])

    geo = parent_comp.create(td.geometryCOMP)
    geo.viewer = True
    geo.nodeX = 0
    geo.nodeY = 0
    geo.render = True
    geo.display = True
    for child in geo.findChildren(depth=1):
        child.destroy()
    inSOP = geo.create(td.inSOP)
    outSOP = geo.create(td.outSOP)
    outSOP.nodeX = 200
    outSOP.setInputs([inSOP])
    outSOP.render = True
    outSOP.display = True
    geo.inputConnectors[0].connect(transform.outputConnectors[0])

    mat = parent_comp.create(td.phongMAT)
    mat.viewer = True
    mat.nodeX = 0
    mat.nodeY = -200
    geo.par.material = mat.name

    render = parent_comp.create(td.renderTOP)
    render.viewer = True
    render.nodeX = 200
    render.nodeY = 0
    render.par.camera = '../camera'
    render.par.geometry = '*'
    render.par.lights = '../light'

    level = parent_comp.create(td.levelTOP)
    level.viewer = True
    level.nodeX = 400
    level.nodeY = 0
    level.setInputs([render])

    out = parent_comp.create(td.outTOP)
    out.viewer = True
    out.nodeX = 600
    out.nodeY = 0
    out.setInputs([level])

    return out


def _set_par(par, value):
    """
    Set a parameter to either a constant value or a TD expression string.

    Args:
        par:   A TouchDesigner parameter object (e.g. transform.par.tx)
        value: A numeric value (int or float) or a TD expression string
               (e.g. "me.time.frame * 0.1")
    """
    if isinstance(value, str):
        par.mode = ParMode.EXPRESSION  # type: ignore
        par.expr = value
    else:
        par.mode = ParMode.CONSTANT    # type: ignore
        par.val = value

# ============================================================
# API COMMANDS
# ============================================================


def box(sizex=1.0, sizey=None, sizez=None, color='white'):
    """
    Create a Box SOP inside a Base COMP and connect it to shapes_composite.

    Args:
        color: Color name (e.g. 'red') or CSS hex string. Applied to the
               Phong material's diffuse color.

    Returns:
        The Base COMP, so it can be stored in the exec namespace for use
        in later commands (e.g. move, remove).
    """
    if sizey is None:
        sizey = sizex

    if sizez is None:
        sizez = sizex

    parent = me.parent()    # type: ignore
    shapes_container = parent.op('shapes')
    name = _auto_name('box')
    color_rgb = parse_color(color)

    shapes = parent.fetch('td_shapes', [])
    node_y = (len(shapes) + 1) * -200

    # Destroy any existing operator with the same name (re-run safety)
    existing = shapes_container.op(name)
    if existing:
        existing.destroy()

    # Create Base COMP container for this shape
    box_base = shapes_container.create(td.baseCOMP, name)
    box_base.nodeX = 0
    box_base.nodeY = node_y
    box_base.viewer = True

    # Build the SOP chain inside the Base COMP
    _create_sop(td.boxSOP, box_base)

    # Apply size to the Box SOP across all three axes
    box_sop = box_base.op('box1')
    if box_sop:
        box_sop.par.sizex = sizex
        box_sop.par.sizey = sizey
        box_sop.par.sizez = sizez

    # Apply color to the Phong material
    mat = box_base.op('phong1')
    if mat:
        mat.par.diffr = color_rgb[0]
        mat.par.diffg = color_rgb[1]
        mat.par.diffb = color_rgb[2]

    # Track shape — newest first so it renders on top in the composite
    shapes.insert(0, name)
    parent.store('td_shapes', shapes)
    _rebuild_composite()

    return box_base


def sphere(radx=0.5, rady=None, radz=None, color='white'):
    if rady is None:
        rady = radx

    if radz is None:
        radz = radx

    parent = me.parent()    # type: ignore
    shapes_container = parent.op('shapes')
    name = _auto_name('sphere')
    color_rgb = parse_color(color)

    shapes = parent.fetch('td_shapes', [])
    node_y = (len(shapes) + 1) * -200

    # Destroy any existing operator with the same name (re-run safety)
    existing = shapes_container.op(name)
    if existing:
        existing.destroy()

    # Create Base COMP container for this shape
    sphere_base = shapes_container.create(td.baseCOMP, name)
    sphere_base.nodeX = 0
    sphere_base.nodeY = node_y
    sphere_base.viewer = True

    # Build the SOP chain inside the Base COMP
    _create_sop(td.sphereSOP, sphere_base)

    # Apply uniform size to the Sphere SOP across all three axes
    sphere_sop = sphere_base.op('sphere1')
    if sphere_sop:
        sphere_sop.par.radx = radx
        sphere_sop.par.rady = rady
        sphere_sop.par.radz = radz

    # Apply color to the Phong material
    mat = sphere_base.op('phong1')
    if mat:
        mat.par.diffr = color_rgb[0]
        mat.par.diffg = color_rgb[1]
        mat.par.diffb = color_rgb[2]

    # Track shape — newest first so it renders on top in the composite
    shapes.insert(0, name)
    parent.store('td_shapes', shapes)
    _rebuild_composite()

    return sphere_base


def torus(radx=0.5, rady=0.25, color='white'):
    parent = me.parent()    # type: ignore
    shapes_container = parent.op('shapes')
    name = _auto_name('torus')
    color_rgb = parse_color(color)

    shapes = parent.fetch('td_shapes', [])
    node_y = (len(shapes) + 1) * -200

    # Destroy any existing operator with the same name (re-run safety)
    existing = shapes_container.op(name)
    if existing:
        existing.destroy()

    # Create Base COMP container for this shape
    torus_base = shapes_container.create(td.baseCOMP, name)
    torus_base.nodeX = 0
    torus_base.nodeY = node_y
    torus_base.viewer = True

    # Build the SOP chain inside the Base COMP
    _create_sop(td.torusSOP, torus_base)

    # Apply uniform size to the Torus SOP across all three axes
    torus_sop = torus_base.op('torus1')
    if torus_sop:
        torus_sop.par.radx = radx
        torus_sop.par.rady = rady

    # Apply color to the Phong material
    mat = torus_base.op('phong1')
    if mat:
        mat.par.diffr = color_rgb[0]
        mat.par.diffg = color_rgb[1]
        mat.par.diffb = color_rgb[2]

    # Track shape — newest first so it renders on top in the composite
    shapes.insert(0, name)
    parent.store('td_shapes', shapes)
    _rebuild_composite()

    return torus_base


def tube(rad1=0.5, rad2=None, height=0.5, color='white'):
    if rad2 is None:
        rad2 = rad1

    parent = me.parent()    # type: ignore
    shapes_container = parent.op('shapes')
    name = _auto_name('tube')
    color_rgb = parse_color(color)

    shapes = parent.fetch('td_shapes', [])
    node_y = (len(shapes) + 1) * -200

    # Destroy any existing operator with the same name (re-run safety)
    existing = shapes_container.op(name)
    if existing:
        existing.destroy()

    # Create Base COMP container for this shape
    tube_base = shapes_container.create(td.baseCOMP, name)
    tube_base.nodeX = 0
    tube_base.nodeY = node_y
    tube_base.viewer = True

    # Build the SOP chain inside the Base COMP
    _create_sop(td.tubeSOP, tube_base)

    # Apply uniform size to the tube SOP across all three axes
    tube_sop = tube_base.op('tube1')
    if tube_sop:
        tube_sop.par.rad1 = rad1
        tube_sop.par.rad2 = rad2
        tube_sop.par.height = height

    # Apply color to the Phong material
    mat = tube_base.op('phong1')
    if mat:
        mat.par.diffr = color_rgb[0]
        mat.par.diffg = color_rgb[1]
        mat.par.diffb = color_rgb[2]

    # Track shape — newest first so it renders on top in the composite
    shapes.insert(0, name)
    parent.store('td_shapes', shapes)
    _rebuild_composite()

    return tube_base


def move(shape, x=0.0, y=0.0, z=0.0):
    """
    Translate a shape by setting its Transform SOP translation parameters.

    Args:
        shape: The Base COMP returned by a shape creation function (e.g. box())
        x:     Translation along the X axis in SOP units (default 0.0)
        y:     Translation along the Y axis in SOP units (default 0.0)
        z:     Translation along the Z axis in SOP units (default 0.0)

    Returns:
        The same Base COMP, so calls can be chained if needed.

    Example:
        b1 = box(0.5, 'blue')
        move(b1, 1.0, 0.5, 0.0)
    """
    if shape is None:
        print("TD API move(): received None shape")
        return

    try:
        transform = shape.op('transform1')
        if not transform:
            print(f"TD API move(): transform1 not found inside {shape.name}")
            return

        _set_par(transform.par.tx, x)
        _set_par(transform.par.ty, y)
        _set_par(transform.par.tz, z)

        return shape

    except Exception as e:
        print(f"TD API move(): error processing shape — {e}")


def rotate(shape, rx=0.0, ry=0.0, rz=0.0):
    """
    Rotate a shape by setting its Transform SOP rotation parameters.

    Args:
        shape: The Base COMP returned by a shape creation function (e.g. box())
        rx:    Rotation around the X axis in degrees (default 0.0)
        ry:    Rotation around the Y axis in degrees (default 0.0)
        rz:    Rotation around the Z axis in degrees (default 0.0)

    Returns:
        The same Base COMP, so calls can be chained if needed.

    Example:
        b1 = box(0.5, 'red')
        rotate(b1, 0, 45, 0)   # rotate 45 degrees around Y axis
    """
    if shape is None:
        print("TD API rotate(): received None shape")
        return

    try:
        transform = shape.op('transform1')
        if not transform:
            print(f"TD API rotate(): transform1 not found inside {shape.name}")
            return

        _set_par(transform.par.rx, rx)
        _set_par(transform.par.ry, ry)
        _set_par(transform.par.rz, rz)

        return shape

    except Exception as e:
        print(f"TD API rotate(): error processing shape — {e}")


def scale(shape, sx=1.0, sy=None, sz=None):
    """
    Scale a shape by setting its Transform SOP per-axis scale parameters.
    Uses sx/sy/sz, leaving the uniform scale parameter free for audio_reactive().

    Args:
        shape: The Base COMP returned by a shape creation function
        sx:    Scale along the X axis (default 1.0)
        sy:    Scale along the Y axis — defaults to sx if not provided
        sz:    Scale along the Z axis — defaults to sx if not provided

    Each value can be a number or a TD expression string.

    Examples:
        scale(b1, 2.0)               # uniform double size
        scale(b1, 2.0, 0.5, 1.0)    # wide, flat, normal depth
        scale(b1, "me.time.frame * 0.01")  # grow over time
    """
    if sy is None:
        sy = sx
    if sz is None:
        sz = sx

    if shape is None:
        print("TD API scale(): received None shape")
        return

    try:
        transform = shape.op('transform1')
        if not transform:
            print(f"TD API scale(): transform1 not found inside {shape.name}")
            return

        _set_par(transform.par.sx, sx)
        _set_par(transform.par.sy, sy)
        _set_par(transform.par.sz, sz)

        return shape

    except Exception as e:
        print(f"TD API scale(): error processing shape — {e}")


def audio_reactive(*shapes, low=0.8, high=1.0):
    """
    Make one or more shapes pulse in scale with the speaker's voice volume.
    Reads the normalized RMS audio signal (0→1) from sound_data_in and
    remaps it to a scale range, applied uniformly to sx, sy, sz on each
    shape's Transform SOP.

    Args:
        *shapes: One or more Base COMPs to make audio-reactive.
                 Accepts any number of positional arguments, e.g.:
                     audio_reactive(b1)
                     audio_reactive(s1, b1, tu1)
        low:  Scale value when silent (default 0.8)
        high: Scale value at peak volume (default 1.0)

    Examples:
        audio_reactive(b1)                      # subtle pulse
        audio_reactive(s1, b1, tu1)             # multiple shapes
        audio_reactive(b2, low=0.5, high=1.5)   # intense pulse
    """
    if not shapes:
        print("TD API audio_reactive(): no shapes provided")
        return

    # TD expression that remaps normalized audio (0→1) to desired scale range
    expr = f"tdu.remap(op('../sound_data_in')['chan1'], 0, 1, {low}, {high})"

    for shape in shapes:
        if shape is None:
            print("TD API audio_reactive(): received None shape, skipping")
            continue

        try:
            transform = shape.op('transform1')
            if not transform:
                print(f"TD API audio_reactive(): transform1 not found inside {shape.name}")
                continue

            transform.par.scale.mode = ParMode.EXPRESSION  # type: ignore
            transform.par.scale.expr = expr

            print(f"TD API audio_reactive(): '{shape.name}' now reactive (low={low}, high={high})")

        except Exception as e:
            print(f"TD API audio_reactive(): error processing shape, skipping — {e}")


def color(shape, color):
    """
    Change the diffuse color of a shape's Phong material at runtime.

    Args:
        shape: The Base COMP returned by a shape creation function
        color: Color name (e.g. 'red') or CSS hex string (e.g. '#FF0000')

    Returns:
        The same Base COMP, so calls can be chained if needed.

    Examples:
        color(b1, 'red')
        color(b1, '#00FF00')
        color(b1, 'emerald')
    """
    if shape is None:
        print("TD API color(): received None shape")
        return

    try:
        mat = shape.op('phong1')
        if not mat:
            print(f"TD API color(): phong1 not found inside {shape.name}")
            return

        rgb = parse_color(color)
        mat.par.diffr = rgb[0]
        mat.par.diffg = rgb[1]
        mat.par.diffb = rgb[2]

        return shape

    except Exception as e:
        print(f"TD API color(): error processing shape — {e}")


def opacity(shape, value=1.0):
    """
    Set the opacity of a shape via its Level TOP.
    Accepts a number (0.0–1.0) or a TD expression string.

    Args:
        shape: The Base COMP returned by a shape creation function
        value: Opacity from 0.0 (invisible) to 1.0 (fully opaque).
               Can be a TD expression string for animated opacity.

    Returns:
        The same Base COMP, so calls can be chained if needed.

    Examples:
        opacity(b1, 0.5)                                          # 50% transparent
        opacity(b1, 0.0)                                          # invisible
        opacity(b1, "abs(math.sin(me.time.frame * 0.05))")        # fade in and out
        opacity(b1, "tdu.remap(op('../sound_data_in')['chan1'], 0, 1, 0.2, 1.0)")  # audio-driven
    """
    if shape is None:
        print("TD API opacity(): received None shape")
        return

    try:
        level = shape.op('level1')
        if not level:
            print(f"TD API opacity(): level1 not found inside {shape.name}")
            return

        _set_par(level.par.opacity, value)

        return shape

    except Exception as e:
        print(f"TD API opacity(): error processing shape — {e}")


def remove(shape):
    """
    Destroy a single shape Base COMP and remove it from tracking.
    Mirrors the browser's remove() function.

    Args:
        shape: The Base COMP returned by a shape creation function,
               e.g. the value stored in b1 after b1 = box(0.5, 'red')

    Returns:
        None — the shape is destroyed and the reference is no longer valid.

    Example:
        b1 = box(0.5, 'red')
        remove(b1)
    """
    if shape is None:
        print("TD API remove(): received None shape")
        return

    try:
        parent = me.parent()    # type: ignore
        shapes_container = parent.op('shapes')
        shapes = parent.fetch('td_shapes', [])
        name = shape.name

        # Remove from tracking list
        if name in shapes:
            shapes.remove(name)
            parent.store('td_shapes', shapes)
        else:
            print(f"TD API remove(): '{name}' not found in td_shapes tracking list")

        # Destroy the Base COMP
        existing = shapes_container.op(name)
        if existing:
            existing.destroy()
        else:
            print(f"TD API remove(): operator '{name}' not found in shapes container")

        # Rebuild composite without the removed shape
        _rebuild_composite()

    except Exception as e:
        print(f"TD API remove(): error processing shape — {e}")


def clear():
    """
    Destroy all dynamically created shape Base COMPs and reset the composite.
    Also clears the persistent execution namespace.
    Mirrors the browser's clear() function.
    """
    parent = me.parent()    # type: ignore
    shapes_container = parent.op('shapes')
    shapes = parent.fetch('td_shapes', [])

    for name in shapes:
        shape_op = shapes_container.op(name)
        if shape_op:
            shape_op.destroy()

    parent.store('td_shapes', [])
    parent.store('td_namespace', {})

    comp = shapes_container.op('shapes_composite')
    if comp:
        for connector in list(comp.inputConnectors):
            connector.disconnect()
