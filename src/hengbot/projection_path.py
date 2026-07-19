"""Hengband's discrete projection rasterizer.

Ported from ``src/target/projection-path-calculator.cpp`` in dis-/hengband.
The firing code uses the same discrete line (``src/combat/shoot.cpp``); callers
may request ``through=True`` to continue the ray beyond the selected aim grid.
"""

from __future__ import annotations

from collections.abc import Callable

from hengbot.model import Position


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def projection_path(
    origin: Position,
    aim: Position,
    max_range: int,
    blocks: Callable[[Position], bool],
    *,
    through: bool = False,
) -> list[Position]:
    """Return traversed grids, including the first blocking grid.

    This preserves ProjectionPath's fractional stepping and its diagonal
    distance accounting.  A through-path keeps the original aim slope until
    range or terrain stops it, matching PROJECT_THRU.
    """
    if origin == aim or max_range <= 0:
        return []

    dy = aim.y - origin.y
    dx = aim.x - origin.x
    half = abs(dy) * abs(dx)
    full = half * 2
    positions: list[Position] = []

    def stopped(pos: Position) -> bool:
        return (not through and pos == aim) or blocks(pos)

    if abs(dy) > abs(dx):
        m = dx * dx * 2
        y, x = origin.y + _sign(dy), origin.x
        frac = m
        k = 0
        if frac > half:
            x += _sign(dx)
            frac -= full
            k += 1
        while True:
            pos = Position(y, x)
            positions.append(pos)
            if len(positions) + k // 2 >= max_range or stopped(pos):
                break
            if m:
                frac += m
                if frac > half:
                    x += _sign(dx)
                    frac -= full
                    k += 1
            y += _sign(dy)
        return positions

    if abs(dx) > abs(dy):
        m = dy * dy * 2
        y, x = origin.y, origin.x + _sign(dx)
        frac = m
        k = 0
        if frac > half:
            y += _sign(dy)
            frac -= full
            k += 1
        while True:
            pos = Position(y, x)
            positions.append(pos)
            if len(positions) + k // 2 >= max_range or stopped(pos):
                break
            if m:
                frac += m
                if frac > half:
                    y += _sign(dy)
                    frac -= full
                    k += 1
            x += _sign(dx)
        return positions

    y = origin.y + _sign(dy)
    x = origin.x + _sign(dx)
    while True:
        pos = Position(y, x)
        positions.append(pos)
        if len(positions) * 3 // 2 >= max_range or stopped(pos):
            break
        y += _sign(dy)
        x += _sign(dx)
    return positions
