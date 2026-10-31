"""What Change Variable Value can do. Unverified until compared with a real room.

The numbers are how a box file stores each operation. Bit positions count from 0, the lowest bit of the 64-bit
value.
"""

from __future__ import annotations

import random

MASK = 2**64 - 1
BITS = 64

OPERATION_LABELS = {
    "set": "Set",
    "add": "Add",
    "subtract": "Subtract",
    "multiply": "Multiply",
    "divide": "Divide",
    "power": "Power",
    "modulo": "Modulo",
    "set_minimum": "Set minimum",
    "set_maximum": "Set maximum",
    "random": "Random",
    "absolute": "Absolute value",
    "bit_and": "Bitwise AND",
    "bit_or": "Bitwise OR",
    "bit_xor": "Bitwise XOR",
    "invert": "Invert",
    "shift_left": "Shift left",
    "shift_right": "Shift right",
    "bit_count": "Count bits",
    "next_low": "Next clear bit, from this position",
    "next_high": "Next set bit, from this position",
    "previous_low": "Previous clear bit, from this position",
    "previous_high": "Previous set bit, from this position",
    "get_bit": "Get bit",
    "set_bit": "Set bit",
    "clear_bit": "Clear bit",
    "toggle_bit": "Toggle bit",
    "next_low_after": "Next clear bit, after this position",
    "next_high_after": "Next set bit, after this position",
    "previous_low_before": "Previous clear bit, before this position",
    "previous_high_before": "Previous set bit, before this position",
}
OPERATION_CODES = {
    0: "set",
    1: "add",
    2: "subtract",
    3: "multiply",
    4: "divide",
    5: "power",
    6: "modulo",
    40: "set_minimum",
    41: "set_maximum",
    50: "random",
    60: "absolute",
    100: "bit_and",
    101: "bit_or",
    102: "bit_xor",
    103: "invert",
    104: "shift_left",
    105: "shift_right",
    110: "bit_count",
    111: "next_low",
    112: "next_high",
    113: "previous_low",
    114: "previous_high",
    115: "get_bit",
    116: "set_bit",
    117: "clear_bit",
    118: "toggle_bit",
    119: "next_low_after",
    120: "next_high_after",
    121: "previous_low_before",
    122: "previous_high_before",
}
# Where a bit search starts, relative to the given position, which way it looks, and the bit it wants.
BIT_SEARCHES = {
    "next_low": (0, 1, 0),
    "next_high": (0, 1, 1),
    "previous_low": (0, -1, 0),
    "previous_high": (0, -1, 1),
    "next_low_after": (1, 1, 0),
    "next_high_after": (1, 1, 1),
    "previous_low_before": (-1, -1, 0),
    "previous_high_before": (-1, -1, 1),
}


def wrap(value: int) -> int:
    """Keeps the low 64 bits as a signed number."""
    value &= MASK
    return value - 2**64 if value >= 2**63 else value


def _divide(current: int, operand: int) -> int:
    if operand == 0:
        return 0 if current == 0 else (2**63 - 1 if current > 0 else -(2**63))
    quotient = abs(current) // abs(operand)
    return wrap(quotient if (current < 0) == (operand < 0) else -quotient)


def _modulo(current: int, operand: int) -> int:
    if operand == 0:
        return 0
    remainder = abs(current) % abs(operand)
    return -remainder if current < 0 else remainder


def _find_bit(current: int, start: int, step: int, wanted: int) -> int:
    position = start
    while 0 <= position < BITS:
        if (current >> position) & 1 == wanted:
            return position
        position += step
    return -1


def _on_bit(operation: str, current: int, position: int) -> int:
    """A position outside the value reads as 0 and changes nothing."""
    if not 0 <= position < BITS:
        return 0 if operation == "get_bit" else current
    bit = 1 << position
    match operation:
        case "get_bit":
            return (current >> position) & 1
        case "set_bit":
            return wrap(current | bit)
        case "clear_bit":
            return wrap(current & ~bit)
        case _:
            return wrap(current ^ bit)


def apply(operation: str, current: int, operand: int, rng: random.Random) -> int:
    """Add, subtract and multiply may leave 64 bits, so the caller keeps them in range."""
    if operation in BIT_SEARCHES:
        offset, step, wanted = BIT_SEARCHES[operation]
        return _find_bit(current, operand + offset, step, wanted)
    match operation:
        case "set":
            return operand
        case "add":
            return current + operand
        case "subtract":
            return current - operand
        case "multiply":
            return current * operand
        case "divide":
            return _divide(current, operand)
        case "power":
            return wrap(pow(current, operand, 2**64)) if operand >= 0 else 1
        case "modulo":
            return _modulo(current, operand)
        case "set_minimum":
            return max(current, operand)
        case "set_maximum":
            return min(current, operand)
        case "random":
            return rng.randint(0, operand) if operand > 0 else 0
        case "absolute":
            return wrap(abs(current))
        case "bit_and":
            return current & operand
        case "bit_or":
            return current | operand
        case "bit_xor":
            return current ^ operand
        case "invert":
            return ~current
        case "shift_left":
            return wrap(current << max(0, min(operand, BITS - 1)))
        case "shift_right":
            return wrap((current & MASK) >> max(0, min(operand, BITS - 1)))
        case "bit_count":
            return (current & MASK).bit_count()
        case "get_bit" | "set_bit" | "clear_bit" | "toggle_bit":
            return _on_bit(operation, current, operand)
    return current
