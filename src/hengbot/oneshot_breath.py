"""A floor where one breath or ball of a known monster kills from full HP (owner 2026-11-08).

Owner, option 「感知で見えたら備える」: 「感知で見えている敵（眠っていても）のブレス・球の最大の被害を、
今の耐性で計算し、最大HP 以上なら、その階では耐性の薬を先に飲むか、薬が無ければ階を離れる。」

Recorded n1-c life-161 (Zombie Magic-Eater, Lv32, max HP 418, Angband 44F, 2026-11-08 00:14):
the amulet's giant ESP showed a sleeping 『ウートガルザ・ロキ』 (race 683, 40d100 FORCE_MAXHP,
BR_COLD) at (30,98) on the boards of turns 3226983-3227072 while the bot walked to a down stair;
it left the ESP range, and 130 boards later a 招き猫's TELE_TO and the Teleportation read in
answer put the player beside it; it woke and one cold breath took the full 418 HP before the next
board.  Its breath: min(4000 / 3, 1600) = 1333 (mspell-damage-calculator.cpp:98-100), through the
Zombie's permanent cold resistance (100 + 2) / 3 = 34% -> 453 (player-status-resist.cpp:160-186,
player-damage.cpp:256 ``dam * rate / 100``): at least the max HP.  With the opposition of a
Potion of Resistance or Resist Cold on top, (34 + 2) / 3 = 12% -> 159.  Its pack held neither
(the Home held three Resist Cold), so the rule leaves the floor.

What is computed (one implementation: the evaluator the combat prediction uses):

- the monsters: every hostile the board shows, in view or by a detection or ESP, asleep or not
  (fair play: the game displayed them), with the static race data.  「その階では」: a monster once
  shown stays known for the floor visit, until its index shows another race or its kill or
  shape-change line follows a board that showed it (monster_memory.seen_or_ended); the floor
  change forgets them all.
- the damage: the largest ``monster_ranged_evaluator.maximum_ability_hp_damage`` over the race's
  breaths (BR_*) and balls (BA_*), from the race's maximum HP (``MonraceKnowledge.max_hp`` is the
  dice maximum: the HP itself for FORCE_MAXHP, the conservative value otherwise).
- the resistances: the five elements' layers are read separately, as the game stacks them
  (player-status-resist.cpp): an immunity (``player.immunities``) is 0; a resistance of the
  equipment or the character (``ability_sources`` equipment/permanent, or the ultimate
  resistance on the status bar, player-status-flags.cpp has_resist_cold) is one layer; the
  opposition (the status bar's resist_acid ... resist_pois while it runs, bot-json-output.cpp) is
  another.  Every other element reads ``player.abilities`` as the combat prediction does
  (policy_combat ``RESIST_FLAG_BY_ABILITY``).

The answer, while a known monster's largest breath or ball is at least the max HP:

- a drink that brings every known monster below the max HP: the opposition the carried potions
  add (quaff-effects.cpp: Resistance all five elements, 1d20+20 turns each; Resist Heat fire and
  Resist Cold cold, 1d10+10).  A single-element potion that alone answers the floor goes before
  the Potion of Resistance (the Black Market's ware, policy_shop's buy-out); else the first potion
  that adds an element a lethal breath needs.  It is drunk again when the opposition lapses while
  the monster is still known on the floor.
- else the floor is left by the existing ESP-threat leave (policy_combat ``_esp_threat_leave_key``,
  the leave of the owner's STRONG detection-only tier): the up stair underfoot, else Word of
  Recall below the walk-out depth, else the walk to the up stair.  While that leave runs and no
  hostile is in view, the rung keeps the board for it (the absorbed light of a dark room woke
  life-161's room); a hostile in view leaves the board to the survival and combat rungs below.

Quest plans: on a quest floor with an approved plan the plan's own order goes first (owner
2026-11-07 「作戦が先・即死だけ例外」): this rung never acts there, and the plans' 即死 rung
(threat_tiers.instant_death_key) is unchanged.  On another quest floor the leave is the return's,
which declines while the quest's exit is locked (policy_town ``_return_exit_locked``); the drink
still stands.

Not modelled (the evaluator's simplifications, unchanged here): the player's vulnerabilities
(player-status-resist.cpp's per += per / 3 or x2), which the snapshot does not show, and the
nuke rate (2 * per + 2) / 5 that the evaluator reads as the poison layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_POTION_RESIST_COLD, SV_POTION_RESISTANCE, TVAL_POTION
from hengbot.monster_ranged_evaluator import (
    ABILITY_ATTRIBUTE,
    TR_IM_ACID,
    TR_IM_COLD,
    TR_IM_ELEC,
    TR_IM_FIRE,
    TR_RES_ACID,
    TR_RES_COLD,
    TR_RES_ELEC,
    TR_RES_FIRE,
    TR_RES_POIS,
    maximum_ability_hp_damage,
)
from hengbot.policy_constants import OPPOSITION_FLAG, RESIST_FLAG_BY_ABILITY
from hengbot.monster_memory import seen_or_ended, shown_by_index
from hengbot.retreat_veto_life import Threat

QUAFF_REASON = "oneshot-breath:quaff"
MEMORY = "_oneshot_breath_visit"

SV_POTION_RESIST_HEAT = 30  # sv-potion-types.h
FIVE = ("acid", "elec", "fire", "cold", "pois")
# The evaluator's attribute -> the element whose layers apply (NUKE reads the poison layers).
ELEMENT_OF = {"ACID": "acid", "ELEC": "elec", "FIRE": "fire", "COLD": "cold", "POIS": "pois",
              "NUKE": "pois"}
RESISTANCE_FLAG = {"acid": TR_RES_ACID, "elec": TR_RES_ELEC, "fire": TR_RES_FIRE,
                   "cold": TR_RES_COLD, "pois": TR_RES_POIS}
IMMUNITY_FLAG = {"acid": TR_IM_ACID, "elec": TR_IM_ELEC, "fire": TR_IM_FIRE, "cold": TR_IM_COLD}
LASTING_SOURCES = frozenset({"equipment", "permanent"})
ULTIMATE_RESISTANCE = "ultimate_resistance"  # the status bar's key (bot-json-output.cpp)
# Single-element potions first: each answers its element alone (quaff-effects.cpp:114-117, 486-494).
DRINKS = ((SV_POTION_RESIST_HEAT, frozenset({"fire"})),
          (SV_POTION_RESIST_COLD, frozenset({"cold"})),
          (SV_POTION_RESISTANCE, frozenset(FIVE)))


@dataclass
class Visit:
    floor_key: tuple
    threats: dict = field(default_factory=dict)  # (index, race) -> Threat
    last_turn: int | None = None


def _attacks(knowledge) -> tuple:
    return tuple(sorted(ability for ability in knowledge.abilities
                        if ability.startswith(("BR_", "BA_"))))


def opposed(player) -> frozenset:
    """The elements whose opposition runs on this board."""
    bar = player.status_bar
    if bar is not None:
        return frozenset(element for element in FIVE if f"resist_{element}" in bar)
    # An emitter without the bar: the temporary source is the opposition (temporary-resistances.cpp).
    return frozenset(element for element in FIVE
                     if "temporary" in player.ability_sources.get(f"resist_{element}", ()))


def _lasting_flags(player) -> frozenset:
    """Every flag but the opposition: the five by their lasting layer, the rest as the prediction."""
    flags = {flag for ability, flag in RESIST_FLAG_BY_ABILITY.items()
             if ability in player.abilities and flag != OPPOSITION_FLAG
             and flag not in RESISTANCE_FLAG.values()}
    ultimate = player.status_bar is not None and ULTIMATE_RESISTANCE in player.status_bar
    for element, flag in RESISTANCE_FLAG.items():
        if ultimate or player.ability_sources.get(f"resist_{element}", frozenset()) & LASTING_SOURCES:
            flags.add(flag)
    flags.update(IMMUNITY_FLAG[element] for element in player.immunities if element in IMMUNITY_FLAG)
    return frozenset(flags)


def largest(knowledge, player, against: frozenset) -> tuple[int, str | None]:
    """The race's largest breath or ball after the player's resistances, ``against`` the
    elements opposed; (0, None) without one."""
    lasting = _lasting_flags(player)
    best = (0, None)
    for ability in _attacks(knowledge):
        element = ELEMENT_OF.get(ABILITY_ATTRIBUTE.get(ability, ""))
        flags = lasting | {OPPOSITION_FLAG} if element in against else lasting
        damage = maximum_ability_hp_damage(ability, knowledge, flags=flags, player_hp=player.hp,
                                           blind=player.blind)
        if damage is not None and damage > best[0]:
            best = (damage, ability)
    return best


def _lethal(knowledge, player, against) -> bool:
    return largest(knowledge, player, against)[0] >= player.max_hp


def _applies(policy, snapshot) -> bool:
    if (snapshot.in_town or snapshot.store is not None or snapshot.inside_arena
            or snapshot.dungeon_level <= 0):
        return False
    quest_id = snapshot.floor_key[2]
    return not (quest_id and policy.approved_quest_strategy(quest_id) is not None)


def observe(policy, snapshot) -> None:
    """Remember the shown monsters that one breath or ball of could kill from full HP without
    any opposition; forget the dead and the changed (once per board)."""
    if not _applies(policy, snapshot):
        return
    visit = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    if visit is None or visit.floor_key != snapshot.floor_key:
        visit = Visit(snapshot.floor_key)
        setattr(policy, MEMORY, visit)
    shown = shown_by_index(snapshot)
    for key, threat in list(visit.threats.items()):
        if seen_or_ended(snapshot, key, threat, shown, visit.last_turn):
            del visit.threats[key]
    knowledge = policy._monrace_knowledge
    for monster in shown.values():
        race = knowledge.get(monster.race_id)
        if (monster.hostile and race is not None
                and _lethal(race, snapshot.player, frozenset())):
            visit.threats[(monster.index, monster.race_id)] = Threat(monster.name, snapshot.turn)
    visit.last_turn = snapshot.turn


def known(policy, snapshot) -> list:
    """The races known on this floor whose breath or ball could kill without opposition."""
    visit = getattr(policy, MEMORY, None)
    if visit is None or visit.floor_key != snapshot.floor_key:
        return []
    knowledge = policy._monrace_knowledge
    return [knowledge[race] for _, race in visit.threats if race in knowledge]


def _held(snapshot, sval):
    return next((item for item in snapshot.inventory
                 if item.tval == TVAL_POTION and item.sval == sval and item.aware and item.count > 0),
                None)


def _drink(snapshot, races, now: frozenset):
    """The potion to drink now, or None when no carried potion makes the floor survivable."""
    player = snapshot.player
    held = [(potion, elements) for sval, elements in DRINKS
            if (potion := _held(snapshot, sval)) is not None]
    reachable = now.union(*(elements for _, elements in held))
    if any(_lethal(race, player, reachable) for race in races):
        return None
    for potion, elements in held:  # one drink answers the floor
        if not elements <= now and not any(_lethal(race, player, now | elements) for race in races):
            return potion
    needed = {ELEMENT_OF.get(ABILITY_ATTRIBUTE.get(ability, "")) for race in races
              for ability in _attacks(race)} - now
    return next((potion for potion, elements in held if elements & needed), None)


def _leave_key(policy, snapshot) -> str | None:
    return policy._esp_threat_leave_key(snapshot, policy._strategic_hostiles(snapshot))


def key(policy, snapshot) -> str | None:
    """The drink or the leave while a known monster's breath or ball kills from full HP."""
    if not _applies(policy, snapshot):
        return None
    player = snapshot.player
    now = opposed(player)
    races = known(policy, snapshot)
    if not any(_lethal(race, player, now) for race in races):
        return None
    potion = _drink(snapshot, races, now)
    if potion is not None:
        policy.last_reason = QUAFF_REASON
        return reserved_item_command(policy, snapshot, "quaff", potion)
    if (policy._returning_to_town or player.recalling) and any(
            monster.hostile for monster in snapshot.visible_monsters):
        return None  # the survival and combat rungs answer what is in view
    return _leave_key(policy, snapshot)


def forget_floor_visit(policy) -> None:
    setattr(policy, MEMORY, None)
