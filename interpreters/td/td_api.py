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
    'red':     [1.0,   0.0,   0.0],
    'green':   [0.0,   1.0,   0.0],
    'blue':    [0.0,   0.0,   1.0],
    'yellow':  [1.0,   1.0,   0.0],
    'cyan':    [0.0,   1.0,   1.0],
    'magenta': [1.0,   0.0,   1.0],
    'white':   [1.0,   1.0,   1.0],
    'black':   [0.0,   0.0,   0.0],
    'orange':  [1.0,   0.647, 0.0],
    'purple':  [0.502, 0.0,   0.502],
    'pink':    [1.0,   0.753, 0.796],
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
        'clear': clear,
        # Future functions registered here:
        # 'sphere': sphere,
        # 'torus':  torus,
        # 'tube':   tube,
        # 'move':   move,
        # 'remove': remove,
    })

    return namespace


def _save_namespace(namespace):
    """
    Save the execution namespace back to parent storage.
    Strips API function references before saving — they are re-injected
    on each call to _get_namespace().
    """
    parent = me.parent()    # type: ignore
    api_keys = {'box', 'clear'}
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

    out = parent_comp.create(td.outTOP)
    out.viewer = True
    out.nodeX = 400
    out.nodeY = 0
    out.setInputs([render])

    return out

# ============================================================
# SHAPE COMMANDS
# These functions are injected into the exec namespace and called
# directly from script commands.
# ============================================================


def box(size=1.0, color='white'):
    """
    Create a Box SOP inside a Base COMP and connect it to shapes_composite.

    Args:
        color: Color name (e.g. 'red') or CSS hex string. Applied to the
               Phong material's diffuse color.

    Returns:
        The Base COMP, so it can be stored in the exec namespace for use
        in later commands (e.g. move, remove).
    """
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

    # Apply uniform size to the Box SOP across all three axes
    box_sop = box_base.op('box1')
    if box_sop:
        box_sop.par.sizex = size
        box_sop.par.sizey = size
        box_sop.par.sizez = size

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

# ============================================================
# UTILITY COMMANDS
# ============================================================


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
