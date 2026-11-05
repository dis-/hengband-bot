"""The facts a "may this wait for a quiet moment" gate reads, one record of them.

Each gate of the dungeon ladder wrote its own test of "is it safe now" from the board and the
policy, and they read different things (maintainability review 2026-11-02, DL3), so a fix to
one reached no other.  A gate reads this record instead and states which facts it asks about.
The record judges nothing: which facts make a moment safe stays each gate's own expression.
"""
from __future__ import annotations

from typing import NamedTuple


class SafetyFacts(NamedTuple):
    in_town: bool
    in_store: bool
    hostile_in_view: bool
    took_damage: bool
    blind: bool
    confused: bool
    stunned: bool
    paralyzed: bool
    hallucinated: bool
    escape_owner: str | None


def of(policy, snapshot) -> SafetyFacts:
    """The facts of this board, as they stand when asked."""
    player = snapshot.player
    return SafetyFacts(
        in_town=snapshot.in_town,
        in_store=snapshot.store is not None,
        hostile_in_view=any(monster.hostile for monster in snapshot.visible_monsters),
        took_damage=getattr(policy, "_took_damage", False),
        blind=player.blind,
        confused=player.confused,
        stunned=player.stunned,
        paralyzed=player.paralyzed,
        hallucinated=player.hallucinated,
        escape_owner=policy._escape_state.owner,
    )
