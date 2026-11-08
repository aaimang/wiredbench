"""The tile drawing of the "in neighbourhood" selectors.

A real box stores one bit per tile of a 21 by 21 square, numbered along a spiral that starts at the
centre and turns x+, y+ (up on screen), x-, y-, each run one longer every second turn. The bits are
packed 32 to an int, lowest bit first.
"""

from __future__ import annotations

from functools import cache

RADIUS = 10
SIZE = RADIUS * 2 + 1
MASK_INTS = (SIZE * SIZE + 31) // 32


@cache
def spiral() -> tuple[tuple[int, int], ...]:
    """Each rank's offset from the centre, with y counted upwards as the drawing shows it."""
    found = [(0, 0)]
    x = y = 0
    step = 1
    while len(found) < SIZE * SIZE:
        for dx, dy, runs in ((1, 0, step), (0, 1, step), (-1, 0, step + 1), (0, -1, step + 1)):
            for _ in range(runs):
                if len(found) == SIZE * SIZE:
                    break
                x, y = x + dx, y + dy
                found.append((x, y))
        step += 2
    return tuple(found)


def square_mask(radius: int) -> list[int]:
    """The ints for a filled square that reaches `radius` tiles out from the centre."""
    radius = max(0, min(RADIUS, radius))
    bits = [max(abs(dx), abs(dy)) <= radius for dx, dy in spiral()]
    return _pack(bits)


def offsets(mask: list[int]) -> list[tuple[int, int]]:
    """The room offsets (x, y) a drawing covers. Room y grows downwards, so the drawing's y flips."""
    found = []
    for rank, (dx, dy) in enumerate(spiral()):
        word, bit = divmod(rank, 32)
        if word < len(mask) and (mask[word] >> bit) & 1:
            found.append((dx, -dy))
    return found


def _pack(bits: list[bool]) -> list[int]:
    words = [0] * MASK_INTS
    for rank, on in enumerate(bits):
        if on:
            words[rank // 32] |= 1 << (rank % 32)
    # Stored as signed 32-bit ints, as a real box saves them.
    return [w - (1 << 32) if w >= 1 << 31 else w for w in words]
