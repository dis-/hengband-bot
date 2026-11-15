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
    # Read by the gates' watcher (safety_watch, owner 2026-11-15 Q9): what the gates differ on.
    hostile_sensed: bool = False     # a hostile known by detection or telepathy only
    hostile_beside: bool = False     # a visible hostile next to the player
    hostile_awake_in_view: bool = False
    poisoned: bool = False
    cut: bool = False
    afraid: bool = False
    hungry: bool = False
    hp_short: bool = False           # below the maximum HP


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
        hostile_sensed=any(monster.hostile for monster in snapshot.detected_monsters),
        hostile_beside=any(monster.hostile and monster.distance <= 1
                           for monster in snapshot.visible_monsters),
        hostile_awake_in_view=any(monster.hostile and not monster.asleep
                                  for monster in snapshot.visible_monsters),
        poisoned=bool(player.poisoned),
        cut=bool(player.cut),
        afraid=bool(player.afraid),
        hungry=bool(player.hungry),
        hp_short=player.hp < player.max_hp,
    )


def strict_quiet(facts: SafetyFacts) -> bool:
    """The strictest gate's reading (junk_destroy_now.safe): no visible hostile, not just hit,
    no store, no impairment, no flight.  The one expression of it."""
    return not (
        facts.in_town or facts.in_store or facts.hostile_in_view or facts.took_damage
        or facts.blind or facts.confused or facts.stunned
        or facts.paralyzed or facts.hallucinated
        or facts.escape_owner not in {None, "return"}
    )
