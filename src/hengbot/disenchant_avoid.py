"""Keep away from what disenchants the gear while the player has no resistance.

Owner 2026-11-05 (disenchant-avoid-decision-20261105): 「劣化耐性がないときに劣化属性攻撃
をするモンスターとの戦闘は可能であれば回避する。クエスト中でなければ*破壊*対象とする。」
Correction the same day: 「ランダムクエストの階であってもターゲットでなければ*破壊*してよい」.

Game (C:/hengband/src):
 * The forms: the blow effect UN_BONUS (monster-attack-switcher.cpp calc_blow_disenchant)
   and the breath BR_DISE (effect-player-resist-hurt.cpp effect_player_disenchant).  No
   other monster spell carries AttributeType::DISENCHANT, and no race in
   MonraceDefinitions.jsonc has AURA_DISENCHANT.  75 races, level 5 to 110.
 * Without resistance every landed blow and every breath calls apply_disenchant
   (spell-kind/spells-equipment.cpp), whatever its damage, so a weak monster is no
   smaller a cost: there is no weakness exemption here.  It picks one of eight slots
   (hands, bow, body, cloak, head, arms, feet); an empty slot or one with no plus does
   nothing; an artifact keeps it 71% of the time.  Otherwise to_h, to_d and to_a each
   lose 1 (one more with chance 1/5 above +5) and pval above 1 loses 1 with chance 1/13.
   The armour smith restores only AC.

Who decides what:
 * ``exposes_gear``: the second trigger of destruction_use (awake, in view, in its
   radius), the owner's 「*破壊*対象」; the floor and target gates are that module's.
 * ``kept_away``: the fight is avoided.  Not on a floor whose exit is locked (no retreat
   exists), and never the hunted quest target or viable guardian (「可能であれば」).
 * ``avoided``: ``kept_away`` unless it strikes from beside the player (survival first:
   walking away from an adjacent hostile donates its blows; a pack is fought one
   adjacent member at a time and the rest stay avoided).
 * ``retreat_key`` uses the existing engagement retreat, and _material_melee_damage makes
   every engagement owner (hunt, retreat, danger cells) answer for it as for a material
   melee threat.  When no retreat step exists, an awake one in range is fought as today
   (``fought``); a sleeper is never woken.  A floor the avoided area closes is left by
   the existing exhausted-floor rules; nothing here teleports or waits.
 * A never-moving one is ringed by immobile_threat_memory (like a stat drainer), so the
   ring and its step-out apply.  immobile_ranged_kill's safe shots (owner 2026-11-02)
   apply to an awake one that can only touch, which cannot disenchant from range;
   ``left_alone`` keeps them from a breather and from a sleeper, unless its ring closes
   the way on (owner 2026-11-05 「通路をふさぐ時だけ撃つ」).
 * ``remembered``: one out of sight stays where it was last shown for the window of the
   retreat's veto (retreat_veto_life.UNSEEN_GAME_TURNS), so the retreat and the routes'
   danger cells (_engagement_danger_cells) still answer for it.  n1-b life-339 (Angband
   30F, 2026-11-08 02:39): a Devilfish (race 918, BR_DISE) swam at [37,81]/[38,81]; at
   [37,84] the retreat stepped to [38,85], where the wall hid it, its danger cells were
   empty, and the explore stepped straight back to [37,84] until the loop detector
   stopped the bot (its veto of [37,84] was not claimed: engagement_avoid_seal).
   It is forgotten when it is shown elsewhere or with another race on its index, when its
   kill line shows (breeder_stalemate.shows_kill), when the player sees its cell empty
   (the certification immobile_threat_memory uses), or after the window.
"""

from __future__ import annotations

from dataclasses import replace

from hengbot import hunt_target, survival_preemption
from hengbot.breeder_stalemate import shows_kill
from hengbot.model import Position
from hengbot.policy_constants import HUNT_RANGE
from hengbot.retreat_veto_life import UNSEEN_GAME_TURNS

BLOW_EFFECTS = frozenset({"UN_BONUS"})    # race-info-tokens-table.cpp
ABILITIES = frozenset({"BR_DISE"})        # mspell-breath.cpp
RESIST_ABILITY = "resist_disen"           # bot-json-output.cpp, TR_RES_DISEN
MEMORY = "_disenchant_avoid_seen"         # (floor, {(index, race): (MonsterState, turn)})


def _race_disenchants(policy, monster) -> bool:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return knowledge is not None and (
        any(blow.effect in BLOW_EFFECTS for blow in knowledge.blows)
        or bool(ABILITIES & knowledge.abilities))


def exposes_gear(policy, snapshot, monster) -> bool:
    """Its blows or breath disenchant, and the player does not resist."""
    return (_race_disenchants(policy, monster)
            and not snapshot.player.ability_sources.get(RESIST_ABILITY))


def kept_away(policy, snapshot, monster) -> bool:
    """The fight with it is avoided while the floor can be left."""
    return (exposes_gear(policy, snapshot, monster)
            and not snapshot.in_town and snapshot.dungeon_level > 0
            and not policy._floor_navigation_exit_locked(snapshot)
            and monster.race_id != hunt_target.target_race(policy, snapshot))


def avoided(policy, snapshot, monster) -> bool:
    """``kept_away``, and it is not striking from beside the player."""
    return (kept_away(policy, snapshot, monster)
            and not survival_preemption.strikes_from_adjacent(policy, snapshot, monster))


def retreat_key(policy, snapshot, hostiles, ringed) -> str | None:
    """The engagement retreat from an avoided monster in range, else None.
    ``ringed``: a never-mover its ring already passes around."""
    hostiles = [*hostiles, *remembered(policy, snapshot)]
    if not any(monster.distance <= HUNT_RANGE and not ringed(policy, monster)
               and avoided(policy, snapshot, monster) for monster in hostiles):
        return None
    return policy._avoid_engagement_key(snapshot, hostiles)


def observe(policy, snapshot) -> None:
    """Every board: remember each kept-away monster shown, forget one that is gone."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        setattr(policy, MEMORY, None)
        return
    memory = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    seen = memory[1] if memory is not None and memory[0] == snapshot.floor_key else {}
    shown = {monster.index: monster for monster in snapshot.visible_monsters}
    for key, (monster, turn) in list(seen.items()):
        now = shown.get(key[0])
        if now is not None:
            if now.race_id != key[1]:
                del seen[key]
        elif (snapshot.turn - turn > UNSEEN_GAME_TURNS
              or shows_kill(snapshot, monster.name)
              or policy._player_can_see_empty_cell(
                  snapshot, monster.position, race_id=monster.race_id)):
            del seen[key]
    for monster in shown.values():
        if monster.hostile and kept_away(policy, snapshot, monster):
            seen[(monster.index, monster.race_id)] = (monster, snapshot.turn)
    setattr(policy, MEMORY, (snapshot.floor_key, seen))


def remembered(policy, snapshot) -> list:
    """The kept-away monsters out of sight, at their last shown cell, within the window."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        return []
    shown = {monster.index for monster in snapshot.visible_monsters}
    here = snapshot.player.position
    return [
        replace(monster, distance=here.distance_to(monster.position))
        for (index, _race), (monster, _turn) in memory[1].items()
        if index not in shown and kept_away(policy, snapshot, monster)
    ]


def remembered_cells(policy, snapshot, ringed) -> frozenset:
    """The cells routes keep off for the ``remembered`` monsters (``ringed``: a never-mover
    its ring already passes around): the engagement retreat's area (HUNT_RANGE around the
    last shown cell), and inside it the cells nearer that cell than the player, so a walk
    from inside never goes further in (where the retreat's own step is vetoed)."""
    here = snapshot.player.position
    cells: set = set()
    for monster in remembered(policy, snapshot):
        if ringed(policy, monster):
            continue
        reach = min(HUNT_RANGE, here.distance_to(monster.position) - 1)
        cells.update(
            Position(monster.position.y + dy, monster.position.x + dx)
            for dy in range(-reach, reach + 1)
            for dx in range(-reach, reach + 1))
    return frozenset(cells)


def left_alone(policy, snapshot, monster, closes_the_way) -> bool:
    """A kept-away never-mover no shot may answer with a breath, or wake with no need:
    ``closes_the_way`` tells whether its ring is what closes the way on."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return (kept_away(policy, snapshot, monster)
            and (bool(ABILITIES & knowledge.abilities)
                 or (monster.asleep and not closes_the_way(policy, snapshot, monster))))


def not_avoided(policy, snapshot, monsters) -> list:
    return [monster for monster in monsters if not avoided(policy, snapshot, monster)]


def fought(policy, snapshot, monsters) -> list:
    """The attack rungs' targets after ``retreat_key`` declined.

    An awake avoided monster still in range had no step away (or is ringed, whose
    shots stay as for a stat drainer): the fight is as today.  A sleeper is left
    asleep, and one beyond the range is not called over."""
    return [monster for monster in monsters
            if not avoided(policy, snapshot, monster)
            or (not monster.asleep and monster.distance <= HUNT_RANGE)]
