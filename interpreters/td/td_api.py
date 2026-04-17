"""
td_api
======
TouchDesigner API for handling execute commands from the listener.
Called by the WebSocket callback DAT via mod(op("td_api")).handle(data)
 
Imports td_command_parser to parse raw command strings into instruction dicts,
then dispatches to the appropriate operator-creation function.
"""

from td_command_parser import parse_td_command


def handle(data):
    """
    Entry point called by the WebSocket callback DAT for execute commands.

    Args:
            data: Parsed JSON dict, e.g.
                  {"target": "td", "command": "execute", "code": "let c1 = circle(50, \\'red\\')"}
    """
    code = data.get("code", "").strip()
    if not code:
        print("TD API: received empty code string")
        return

    print(f"TD API executing: {code}")

    try:
        instruction = parse_td_command(code)
        _dispatch(instruction)
    except ValueError as e:
        print(f"TD API parse error: {e}")


def _dispatch(instruction):
    """Route a parsed instruction dict to the appropriate handler."""
    op_type = instruction.get("type")

    if op_type == "circle":
        create_circle(instruction)
    elif op_type == "clear":
        clear()
    else:
        print(f"TD API: unknown instruction type \'{op_type}\'")


def create_circle(instruction):
    """
    Create a Circle TOP and connect it to the Composite TOP.

    Args:
            instruction: {"type": "circle", "name": "c1", "radius": 50, "color": [r, g, b]}
    """
    # Placeholder — full implementation in next step
    print(f"TD API: create_circle called with {instruction}")


def clear():
    """Remove all dynamically created shape operators."""
    # Placeholder — full implementation in next step
    print("TD API: clear called")
