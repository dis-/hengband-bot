"""A recall landing on a dungeon's last floor whose guardian is T1 is no destination.

Owner 2026-11-10 (the n1-b life-367 report's P3, verbatim): 「守護者が T1 の最下層は、*破壊* の
有無に関係なく帰還先にしない。」  n1-b recalled to the Mountain 50F, its last floor, 116 times in a
day; 大鷲王『ソロンドール』 (speed +35, summons) is placed there on every generation and read T1,
so the sensed-T1 leave ended dive after dive.

The guardian floor is the dungeon's ``max_depth`` (DungeonDefinitions final_floor.guardian, placed
by the game on the last floor), until the dungeon is conquered.  Its tier is the threat tiers'
reading (threat_tiers ``tiered``, contact=True, the hunted guardian's reading in
hunt_target._guardian_beatable) on the duel board ``_guardian_fight_viable`` builds: the race's
static data (lib/edit/MonraceDefinitions.jsonc, fair play), adjacent, at its average HP, against
the player at full HP with the pack as it is.  Only T1 refuses: an undecided reading (the
projection's cost cap) is not T1.

Askers: the recall landing checks (policy ``_recall_landing_guardian_blocked``, so the voluntary
recall, the guardian valve's Angband and every alternate that asks ``_recall_destination_safe``)
and the alternates' own landing check (policy_helpers ``_fallback_landing_allowed``); the
deepest-that-fits rule (owner 2026-11-10 「収まる中で一番深い所へ」) then picks among the rest.
"""

from __future__ import annotations

from dataclasses import replace

from hengbot.item_reservation import decision_memo
from hengbot.model import GridState, MonsterState, Position


def _duel(policy, snapshot, info):
    knowledge = policy._monrace_knowledge.get(info.guardian_id)
    if knowledge is None:
        return None
    hp = knowledge.average_hp or knowledge.max_hp
    player_position, target_position = Position(10, 10), Position(10, 11)
    guardian = MonsterState(
        index=-info.guardian_id, position=target_position, hp=hp, max_hp=hp, distance=1,
        friendly=knowledge.friendly, pet=False, speed=knowledge.speed,
        name=f"guardian:{info.guardian_id}", race_id=info.guardian_id,
        can_summon=knowledge.can_summon, level=knowledge.level,
        max_melee_damage=knowledge.max_melee_damage,
        max_ranged_damage=knowledge.max_ranged_damage, can_multiply=knowledge.can_multiply)
    grids = {
        player_position: GridState(player_position, True, True, False, False, False, False, False),
        target_position: GridState(target_position, True, True, False, True, False, False, False),
    }
    board = replace(snapshot, player=replace(snapshot.player, position=player_position,
                                             hp=snapshot.player.max_hp),
                    grids=grids, visible_monsters=[guardian], detected_monsters=[], store=None)
    return board, guardian


def guardian_tier(policy, snapshot, info) -> str | None:
    """The tier of ``info``'s guardian alone at contact on the duel board, else None."""
    def compute():
        from hengbot import threat_tiers

        duel = _duel(policy, snapshot, info)
        if duel is None:
            return None
        board, guardian = duel
        return threat_tiers.tiered(policy, board, [guardian], contact=True).tier
    return decision_memo(policy, "guardian_landing.tier", snapshot, info.id, compute)


def t1_landing(policy, snapshot, dungeon_id: int, depth: int) -> bool:
    """``depth`` of ``dungeon_id`` is its unconquered last floor and the guardian there is T1."""
    from hengbot import threat_tiers

    info = policy._dungeon_knowledge.get(dungeon_id)
    return bool(
        info is not None
        and info.guardian_id > 0
        and info.max_depth > 0
        and depth >= info.max_depth
        and dungeon_id not in snapshot.conquered_dungeon_ids
        and guardian_tier(policy, snapshot, info) == threat_tiers.T1
    )
