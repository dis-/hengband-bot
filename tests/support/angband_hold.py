"""A declared wall for pins whose subject predates the Angband 50F hold.

Owner 2026-11-19 (verbatim): 「鉄獄50F以降は浅い階層へのフォールバックをやめる。行き先を変えるのはダンジョンの
主討伐のみとする。」 (``hengbot.angband_hold``).  Several older pins prove a fallback's mechanics (the
over-extension lease's counting and doubling, the deepest destination, the fallback depth floor, the
Castle/Mountain dive and band) on a board whose Angband landing is 50F or deeper; the mechanics stay
for a character shallower than that.  This wall raises the hold depth past every dungeon so the
pre-hold subject is still exercised; tests/test_angband_hold_1119_recorded.py and the held variants
next to each use pin what the hold does on those boards.  DECLARED WALL wherever it is used.
"""

from __future__ import annotations

from unittest import mock

from hengbot import angband_hold


def hold_lifted():
    """No character is held (the hold depth is deeper than any dungeon)."""
    return mock.patch.object(angband_hold, "HOLD_DEPTH", 1000)
