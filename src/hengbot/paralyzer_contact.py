"""D55: a paralyzer is in contact when its blow can land before our next action.

Recorded n1-a life-450 (Labyrinth 16F, 2026-10-31 14:47): the Lv24 warrior
without Free Action waited on Word of Recall carrying 12 Teleportation
scrolls.  An アイス・コボルド stepped beside it and a ランゴスタ (race 1252,
speed +10, STING/CRUSH PARALYZE) stood two cells away.  The paralyzer rung
(``_paralyzer_prevention_key``, which reads an escape scroll before a
paralyzer's blow lands) looked at adjacency only and saw none; the
status-threat rung below it then kept the fight already in contact.  The bot
meleed the kobold; the locust, with two actions per player action, closed and
stung, and the player died paralyzed at HP 213/419 (playrecord
「麻痺状態でランゴスタに殺された」).

Only the paralyzer rung reads contact.  When it has neither a scroll nor a
retreat step, the status-threat rung's "finish the fight already in contact"
still melees the adjacent enemy, which beats a status-threat wait.

Contact is the game's energy arithmetic, not a new margin: each game tick
the player and every monster lose ``speed_to_energy(speed)`` of their energy
need (core/player-processor.cpp:133, monster/monster-processor.cpp:677) and
every action costs ``ENERGY_NEED()`` = randnor(100, 25)
(core/speed-table.h:6), so between two player actions a monster takes on
average ``monster_energy // player_energy`` actions; one ``path`` steps away
needs ``path - 1`` moves and one blow.
"""

from __future__ import annotations


def in_contact(policy, snapshot, monster) -> bool:
    """Whether ``monster``'s melee can reach the player before its next action."""
    if monster.distance <= 1:
        return True
    if monster.asleep:
        return False
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is not None and "NEVER_MOVE" in knowledge.flags:
        return False
    path = policy._monster_path_distance(snapshot, monster.position)
    if path is None:
        return False
    actions = policy._speed_energy(monster.speed) // policy._speed_energy(
        snapshot.player.speed
    )
    return actions >= path
