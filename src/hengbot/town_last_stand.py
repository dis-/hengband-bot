"""Fight an adjacent town attacker when nothing else is carried (#47, 死2).

USER DECISION 2026-10-31: 「店の中では時間経過しないので逃げ込む行動に意味は
ない。本当に物資がなく、街の敵にも勝てないくらい弱いなら先はないので諦めて
戦闘を試みる。」

In town, with no healing potion and no escape scroll carried, a step away from
an adjacent attacker only donates its next blows: n1-c life-056 (2026-10-31)
fled a step from a Scruffy-looking horse, walked back, and fled again until it
died.  The flee rungs ask this module first and attack instead.  The hunt
itself never walks toward a monster it cannot beat
(``TownMixin._town_monster_unbeatable``).
"""

from __future__ import annotations


def target(policy, snapshot, hostiles):
    """The adjacent attacker to fight instead of a bare flee step, or None."""
    player = snapshot.player
    if (
        # Only the emitter's town flag: the surface wilderness shares the
        # town's floor key and is not covered by the decision.
        snapshot.town_flag is not True
        or snapshot.dungeon_level != 0
        or player.afraid
        or not policy._can_fight_in_dungeon(0)
        or policy._find_heal_potion(snapshot) is not None
        or policy._escape_scroll(snapshot) is not None
    ):
        return None
    adjacent = [
        monster for monster in hostiles
        if player.position.distance_to(monster.position) <= 1
    ]
    return policy._weakest(adjacent) if adjacent else None


def key(policy, snapshot, hostiles, reason: str) -> str | None:
    """Melee that attacker (D21's ranged-first answer is dungeon-only)."""
    monster = target(policy, snapshot, hostiles)
    if monster is None:
        return None
    policy.last_reason = reason
    return policy._direction_key(snapshot.player.position, monster.position)
