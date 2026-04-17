#!/usr/bin/env python3
"""
td_command_parser.py
====================
Parses TD command strings into structured instruction dicts for td_api.py.
The td: prefix is stripped by listen.py before the command string arrives here.
 
Supports two forms:
    Assignment:  let c1 = circle(50, "red")
    Bare call:   circle(50, "red")
 
Output:
    {
        "type": "circle",
        "name": "c1",
        "radius": 50,
        "color": [1.0, 0.0, 0.0]
    }
"""

import re
import ast

# ============================================================
# COLOR MAP
# Matches the color names defined in paper_and_anime_playground.html
# Values are normalized RGB [0.0 - 1.0]
# ============================================================
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

# ============================================================
# REGEX PATTERNS
# ============================================================

# Matches: let c1 = circle(50, "red")
ASSIGNMENT_PATTERN = re.compile(r'let\s+(\w+)\s*=\s*(\w+)\((.*)\)', re.DOTALL)

# Matches: circle(50, "red")  — no assignment
CALL_PATTERN = re.compile(r'(\w+)\((.*)\)', re.DOTALL)

# ============================================================
# HELPERS
# ============================================================


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


def parse_args(args_str):
    """
    Safely parse a comma-separated argument string into a Python list.
    Uses ast.literal_eval rather than eval() to avoid arbitrary code execution.

    Args:
        args_str: Raw argument string, e.g. '50, "red"'

    Returns:
        Python list of parsed values, e.g. [50, 'red']

    Raises:
        ValueError: If the argument string cannot be parsed
    """
    try:
        return ast.literal_eval(f"[{args_str.strip()}]")
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"Could not parse arguments '{args_str}': {e}")


# ============================================================
# COMMAND BUILDERS
# Each function takes (name, args) and returns a structured dict.
# Add a new function here and register it in COMMAND_BUILDERS
# to support a new TD command.
# ============================================================


def build_circle(name, args):
    """
    circle(radius, color)

    Args:
        name: Operator name in TD (from variable assignment, e.g. "c1")
        args: Parsed argument list [radius, color]

    Returns:
        {
            "type": "circle",
            "name": "c1",
            "radius": 50,
            "color": [1.0, 0.0, 0.0]
        }
    """
    if len(args) < 2:
        raise ValueError(
            f"circle() requires at least 2 arguments (radius, color), got {len(args)}"
        )
    return {
        "type": "circle",
        "name": name,
        "radius": args[0],
        "color": parse_color(args[1]),
    }


COMMAND_BUILDERS = {
    'circle': build_circle,
    # Future commands registered here:
    # 'rect':    build_rect,
    # 'move':    build_move,
    # 'remove':  build_remove,
    # 'clear':   build_clear,
}


# ============================================================
# MAIN PARSER
# ============================================================

def parse_td_command(raw):
    """
    Parse a raw TD command string into a structured instruction dict.

    The td: prefix is stripped by listen.py before sending, so this
    function receives only the command body.

    Args:
        raw: Command body string, e.g. "let c1 = circle(50, 'red')"

    Returns:
        Structured instruction dict for td_api.py to act on,
        e.g. {"type": "circle", "name": "c1", "radius": 50, "color": [...]}

    Raises:
        ValueError: If the command is malformed or uses an unsupported function name
    """
    raw = raw.strip()

    # Try assignment form first: let c1 = circle(50, "red")
    match = ASSIGNMENT_PATTERN.match(raw)
    if match:
        var_name = match.group(1)
        func_name = match.group(2)
        args_str = match.group(3)
    else:
        # Fall back to bare call form: circle(50, "red")
        match = CALL_PATTERN.match(raw)
        if match:
            var_name = None
            func_name = match.group(1)
            args_str = match.group(2)
        else:
            raise ValueError(f"Could not parse TD command: '{raw}'")

    if func_name not in COMMAND_BUILDERS:
        raise ValueError(
            f"Unknown TD command: '{func_name}'. "
            f"Supported commands: {list(COMMAND_BUILDERS.keys())}"
        )

    args = parse_args(args_str)
    return COMMAND_BUILDERS[func_name](var_name, args)


# ============================================================
# SELF-TEST
# Run directly to verify parsing without needing the full stack:
#   python td_command_parser.py
# ============================================================

if __name__ == '__main__':
    tests = [
        # (input, should_raise)
        ('let c1 = circle(50, "red")',        False),
        ("let myCircle = circle(100, 'blue')", False),
        ('let bg = circle(960, "#FFA500")',    False),
        ('circle(50, "red")',                  False),  # bare call, no name
        ('let c1 = circle(50)',                True),   # missing color arg
        ('let c1 = rotate(50, "red")',         True),   # unsupported command
        ('not a valid command',                True),   # unparseable
    ]

    passed = 0
    failed = 0

    for raw, should_raise in tests:
        print(f"Input:  {raw}")
        try:
            result = parse_td_command(raw)
            if should_raise:
                print(f"  FAIL — expected an error but got: {result}\n")
                failed += 1
            else:
                print(f"  Output: {result}")
                print(f"  PASS\n")
                passed += 1
        except ValueError as e:
            if should_raise:
                print(f"  Raised ValueError (expected): {e}")
                print(f"  PASS\n")
                passed += 1
            else:
                print(f"  FAIL — unexpected error: {e}\n")
                failed += 1

    print(f"Results: {passed} passed, {failed} failed")
