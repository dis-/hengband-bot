"""A declared wall for pins whose subject predates the fallback depth floor.

Owner 2026-11-13 (verbatim): 「n1-cがまた23Fに落ちている。フォールバックは最新到達-20Fまでにする。」
(``hengbot.fallback_depth_floor``).  Several older pins prove a subject that is not the floor
(which dungeon a valve orders first, what bounds a refused depth, the lease's counting) on a
board whose fallback landings lie more than 20 floors above the deepest reached.  Each such pin
also asserts what the floor does on its board; this wall widens the span past every landing so
the pre-floor subject is still exercised.  DECLARED WALL wherever it is used.
"""

from __future__ import annotations

from unittest import mock

from hengbot import fallback_depth_floor


def floor_lifted():
    """The floor at or below every landing (the span is wider than any dungeon)."""
    return mock.patch.object(fallback_depth_floor, "FALLBACK_DEPTH_SPAN", 1000)
