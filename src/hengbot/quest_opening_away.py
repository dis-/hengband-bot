"""The quest plan's opening Teleport Away (owner 2026-11-02, n1c-death-1102).

Owner: 「テレポートアウェイがあるなら初手でフォルンをどかす。その後の行動は作戦通り。」

Q31's Huorns and Old Man Willow never move (NEVER_MOVE) but cast TELE_TO,
which pulls the player beside the caster (mspell/mspell-floor.cpp:173-190
spell_RF6_TELE_TO -> teleport_player_to).  A monster casts only within
get_max_range() (18, system/angband-system.cpp:45-48; mspell-attack.cpp:319)
and with a projectable line to the player (mspell/mspell-lite.cpp:209-215
decide_lite_projection), so a stationary caster with a clear line to the hold
can pull the player out of it.  Teleport Away is a PROJECT_BEAM of AWAY_ALL
along the aimed line (spell-kind/spells-teleport.cpp:91-95): the beam needs
the projectable line, not the sight of the target, and moves a NEVER_MOVE
monster like any other (teleport_away, spells-teleport.cpp:109-170, and
cave_monster_teleportable_bold, grid/grid.cpp:897-926, look at the
destination only); only RES_TELE resists (effect/effect-monster-evil.cpp:7-30).

Which targets: the approved strategy names them, ``engagement_plan.
opening_teleport_away`` rows ``{"race_id", "target", "stand"}`` (the fixed map
of lib/edit/quests, the same public layout as ``throwing_points``).  From its
stand, before the plan's first action, the absorbed Teleport Away
(me_powers ``quest-opening-target``) is aimed at each target once per floor
visit.  A target cell the player sees empty is skipped.  Without a charged
Teleport Away nothing is sent and the plan runs as before; the survival rungs
of the dungeon ladder ask first.
"""

from __future__ import annotations

from hengbot import me_powers
from hengbot.model import Position


PLAN_KEY = "opening_teleport_away"


def targets(policy, snapshot, profile) -> list[Position]:
    """The plan's opening targets from the player's cell that are not seen empty."""
    here = snapshot.player.position
    found = []
    for row in profile.engagement_plan.get(PLAN_KEY, ()):
        if Position(*row["stand"]) != here:
            continue
        target = Position(*row["target"])
        race_id = int(row["race_id"])
        occupant = next((monster for monster in snapshot.visible_monsters
                         if monster.position == target), None)
        if occupant is not None and occupant.race_id != race_id:
            continue
        if policy._player_can_see_empty_cell(snapshot, target, race_id=race_id):
            continue
        found.append(target)
    return found


def key(policy, snapshot, profile) -> str | None:
    """The Teleport Away key aimed at the first due opening target, else None."""
    for target in targets(policy, snapshot, profile):
        if (sent := me_powers.power_key(policy, snapshot, me_powers.QUEST_OPENING, target)) is not None:
            return sent
    return None
