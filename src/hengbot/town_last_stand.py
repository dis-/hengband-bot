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

D55 (n1-c life-077, 2026-11-01 03:25): the stand is the town fight of the
owner rule 2026-10-31 「近接以外の攻撃手段も街で使う」, so it answers with the
Magic-Eater's ranged order first (``me_ranged_first``) and melees only when
that order has nothing.  The Lv8 Magic-Eater, cornered by 見習戦士 with its
teleport scrolls spent, meleed at to-hit -63 and missed every blow until it
died, carrying the absorbed Magic Missile and sixteen spare lit torches.
"""

from __future__ import annotations

from hengbot import combat_answer


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
    """Fight that attacker: the ranged order first, else melee."""
    monster = target(policy, snapshot, hostiles)
    if monster is None:
        return None
    return combat_answer.strike_key(policy, snapshot, monster, reason)
