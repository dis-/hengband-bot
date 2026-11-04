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
   ``left_alone`` keeps them from a sleeper and from a breather.
"""

from __future__ import annotations

from hengbot import hunt_target, survival_preemption
from hengbot.policy_constants import HUNT_RANGE

BLOW_EFFECTS = frozenset({"UN_BONUS"})    # race-info-tokens-table.cpp
ABILITIES = frozenset({"BR_DISE"})        # mspell-breath.cpp
RESIST_ABILITY = "resist_disen"           # bot-json-output.cpp, TR_RES_DISEN


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
    if not any(monster.distance <= HUNT_RANGE and not ringed(policy, monster)
               and avoided(policy, snapshot, monster) for monster in hostiles):
        return None
    return policy._avoid_engagement_key(snapshot, hostiles)


def left_alone(policy, snapshot, monster) -> bool:
    """A kept-away never-mover no shot may wake or answer with a breath."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    return (kept_away(policy, snapshot, monster)
            and (monster.asleep or bool(ABILITIES & knowledge.abilities)))


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
