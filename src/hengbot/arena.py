"""The Telmora arena (owner 2026-11-05).

Owner: 「ダンジョンに出発する前に闘技場に挑むかの判定を行う。街の移動資金が往復分あり、次の
対戦相手への勝率が90%以上なら挑戦する。勝利して報酬を得た場合は街の処理を最初からやり直す。」
「魔法や取り込んだ魔道具は使える。召喚魔法はお互いに使用できない。」

Game facts (src/market/arena*.cpp, floor-generator.cpp, cmd-building.cpp, live capture
tests/fixtures/arena-live-1105.json.gz):

* The building is type 2, in Telmora (town id 1) only.  Stepping on it opens the menu:
  ``e`` enters, ``p`` prints the poster (no time, no gold).
* One loss closes it for good: the step prints 「敗者に用はない。」 and opens no menu.
* The floor reports ``inside_arena`` with in_town true and level 0, the same floor key
  as a town.  ``parse_snapshot`` gives it its own key and takes it out of town, so the
  way back is a floor change: the town visit starts over by itself (``is_fresh_visit``),
  after a win and after a loss.  That is 「街の処理を最初からやり直す」.
* The player stands on the gate; the opponent is 5 cells below.  The floor is lit, so a
  monster not in view is dead or invisible.  Scrolls, potions, staffs, wands, rods,
  activation and throwing are refused without a turn (cmd_limit_arena); absorbed powers,
  spells and the launcher work.  Summons and TELE_LEVEL are off for the monster.
* A character at HP below 0 in the arena does not die: HP 0, back on the building's cell in
  town, defeated (decide_arena_death).
* The reward drops at the monster (drop_near).  The gate opens after the kill; a step onto
  it leaves and reopens the building's menu, which the executor closes.  With the monster
  alive the step prints 「ゲートは閉まっている。」 on row 0 only.

The standing is read from the character sheet: ``闘技場: N勝`` is the game's own count of
the fights won, written by the departure dump right before this owner asks.  Without a
sheet the opponent is unknown and the character does not fight.  The poster is checked
against the table before entering, so a sheet that lags cannot start the wrong fight.

Round trip (「街の移動資金が往復分あり」): from any other town two inn fares; in Telmora
none, because the way back is already held by the fare reserve of every town other than
the Outpost (_outpost_return_fare, owner 2026-10-26).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from hengbot import (
    arena_fight_chain, armor_smith, arena_odds, attack_expectation, blind_strike, combat_answer,
    me_absorbed_substitutes, me_capability, me_device_attacks, me_powers, me_ranged_first,
    morivant_tower, unseen_strike,
)
from hengbot.character_sheet import (
    SHEET_ENCODINGS, ArenaStanding, CharacterSheetUnavailable, _decode_sheet, arena_standing,
)
from hengbot.item_reservation import reserved_item_command
from hengbot.model import SV_STAFF_SPEED
from hengbot.policy_constants import LEAVE_STORE_KEY, TOWN_TELEPORT_COST, WAIT_KEY
from hengbot.quest_navigator import PICKUP_KEY

TELMORA_TOWN_ID = 1
ARENA_BUILDING = 2  # BUILDING_02, cmd-building.cpp ``which == 2``
ENTER_KEY = "e"
POSTER_KEY = "p"
FAMILY = "cross-town"  # the claim family of this owner's town keys

TRAVEL_REASON = "town:arena:travel"
RETURN_REASON = "town:arena:return"
APPROACH_REASON = "town:arena:approach"
POSTER_REASON = "town:arena:poster"
ENTER_REASON = "town:arena:enter"
INN_WALK_REASONS = (TRAVEL_REASON, RETURN_REASON)
POSTER_KEY_PATTERN = rf"[1-9]{POSTER_KEY}{LEAVE_STORE_KEY}"
ENTER_KEY_PATTERN = rf"[1-9]{ENTER_KEY}"

MELEE_REASON = "arena:melee"
WALK_REASON = "arena:walk"
HOLD_REASON = "arena:hold"
STRIKE_REASON = "arena:unseen-strike"
BLIND_STRIKE_REASON = "arena:blind-strike"
REWARD_REASON = "arena:reward"
PICKUP_REASON = "arena:pickup"
GATE_REASON = "arena:gate"
HEAL_REASON = "arena:heal" + me_absorbed_substitutes.CAST_SUFFIX
SPEED_REASON = "arena:speed" + me_absorbed_substitutes.CAST_SUFFIX
# Attacks while the floor's monster is unseen: a gate that stays shut means it lives.
GATE_ATTEMPTS = 2

LOSER_TEXTS = ("敗者に用はない", "no place here for a LOSER")
BEATEN_TEXTS = ("の前に敗れ去った", "You are beaten by")
_POSTER = re.compile(r"(.+?) ?に挑戦するものはいないか|Do I hear any challenges against: (.+)")
_VICTOR_POSTERS = ("あなたは勝利者だ", "You are victorious", "すべての敵に勝利した",
                   "You have won against all foes")
# arena-entry.cpp ARENA_ENTRIES, the race id of each fight (system/enums/monrace/monrace-id.h).
# Entry 41 is the ceremony (1,000,000 gold) and 42 the はぐれメタル: past this table the
# arena is finished for this owner (a question for the owner in its report).
OPPONENTS = (
    1059, 1060, 296, 19, 224, 339, 332, 334, 357, 900,
    483, 435, 490, 1056, 1062, 557, 690, 699, 1061, 894,
    609, 652, 646, 1180, 691, 1187, 720, 1058, 768, 705,
    1178, 737, 774, 1185, 778, 930, 1064, 786, 798, 988,
    847,
)


@dataclass
class ArenaStay:
    """This stay in town's facts: the fights and the inn's hops stay in it."""
    origin: int | None = None  # the town the trip left
    holding: bool = False  # the trip holds the town's board (walks, inn, building)
    returning: bool = False
    travelled: bool = False  # the trip has started; a win opens it again
    closed: bool = False  # a leg or the poster failed: the read goes on
    expected: int | None = None  # the race judged for this entry
    poster_posted: bool = False
    poster_checked: bool = False
    inside: bool = False  # on the arena's floor: leaving it ends the fight's facts
    gate_attempts: int = 0
    tried_reward_cells: set = field(default_factory=set)
    odds: dict = field(default_factory=dict)
    last_verdict: dict | None = None
    progress: tuple | None = None
    positions: dict = field(default_factory=dict)


def state(policy) -> ArenaStay:
    record = getattr(policy, "_arena_stay", None)
    if record is None:
        record = policy._arena_stay = ArenaStay()
    return record


def over_for_good(policy) -> bool:
    return bool(getattr(policy, "_arena_defeated", False))


def _says(snapshot, texts) -> bool:
    return any(text in message for message in snapshot.messages for text in texts)


def observe(policy, snapshot) -> None:
    """Every decision: the loss, the fight's start, a dungeon floor ends the stay."""
    if _says(snapshot, BEATEN_TEXTS) or _says(snapshot, LOSER_TEXTS):
        policy._arena_defeated = True
    if snapshot.floor_key[1] > 0:
        policy._arena_stay = None
        return
    if not snapshot.inside_arena:
        if getattr(policy, "_arena_stay", None) is not None:
            policy._arena_stay.inside = False
        return
    record = state(policy)
    if not record.inside:
        # A new fight: the last one's gate and reward say nothing about it (n1-c life-145
        # 2026-11-05, a chain of wins: it held on an open gate until it starved).
        record.inside = True
        record.gate_attempts = 0
        record.tried_reward_cells = set()
    record.holding = False
    record.travelled = False  # one fight is progress: the next judgement may travel
    record.poster_posted = record.poster_checked = False


def standing(policy) -> ArenaStanding | None:
    """The departure dump's arena line; None without this visit's sheet."""
    path = getattr(policy, "_character_dump_path", None)
    if path is None or not getattr(policy, "_char_dump_done_this_visit", False):
        return None
    try:
        return arena_standing(_decode_sheet(path.read_bytes(), SHEET_ENCODINGS))
    except (OSError, CharacterSheetUnavailable):
        return None


def _signature(policy, snapshot, race_id: int) -> tuple:
    player = snapshot.player
    lists = getattr(policy, "_me_device_lists", None) or {}
    return (race_id, player.hp, player.speed, player.ac, frozenset(player.abilities),
            tuple(item.name for item in snapshot.equipment),
            tuple(sorted((kind, turn) for kind, (turn, _rows) in lists.items())))


def judge(policy, snapshot, record, town: int) -> dict:
    """The owner's two conditions.  ``go`` is the decision; the rest is its record."""
    verdict = {"go": False, "town": town, "gold": snapshot.player.gold}
    known = standing(policy)
    if over_for_good(policy) or (known is not None and known.defeated):
        policy._arena_defeated = True
        return {**verdict, "why": "defeated"}
    if known is None or known.wins is None:
        return {**verdict, "why": "standing-unknown"}
    if known.champion or known.wins >= len(OPPONENTS):
        return {**verdict, "why": "finished"}
    race_id = OPPONENTS[known.wins]
    fare = 0 if town == TELMORA_TOWN_ID else 2 * TOWN_TELEPORT_COST
    verdict.update(wins=known.wins, race_id=race_id, fare=fare)
    if snapshot.player.gold < fare:
        return {**verdict, "why": "fare"}
    if town != TELMORA_TOWN_ID and TELMORA_TOWN_ID not in (snapshot.visited_town_ids or ()):
        return {**verdict, "why": "telmora-unvisited"}
    signature = _signature(policy, snapshot, race_id)
    odds = record.odds.get(signature)
    if odds is None:
        odds = record.odds[signature] = arena_odds.judge(policy, snapshot, race_id)
    verdict.update(chance=odds.chance, refusal=odds.refusal, plan=odds.plan,
                   damage=odds.damage_per_action, kill_actions=odds.kill_actions)
    if not odds.accepted:
        return {**verdict, "why": odds.refusal or "chance"}
    return {**verdict, "go": True, "why": "accepted"}


def _close(record) -> None:
    """A leg cannot go on or the poster disagrees: the read goes on."""
    record.closed = True
    record.holding = record.returning = False
    record.origin = None


def _leg_key(policy, snapshot, record, destination: int, reason: str) -> str | None:
    if armor_smith.no_progress(record, snapshot):
        return _close(record)
    key = policy._town_teleport_key(snapshot, destination, producer=FAMILY, reason=reason)
    return key if key is not None else _close(record)


def _poster_agrees(policy, snapshot, race_id: int) -> bool:
    """The last poster message names the race the table says is next."""
    names = getattr(policy._monrace_knowledge.get(race_id), "names", ())
    for message in reversed(snapshot.messages):
        if any(text in message for text in _VICTOR_POSTERS):
            return False
        found = _POSTER.search(message)
        if found is not None:
            return (found.group(1) or found.group(2)).strip() in names
    return False


def _building_key(policy, snapshot, record, tail: str, reason: str) -> str | None:
    """The walk to the building, or the step onto it with ``tail``."""
    step, enters = morivant_tower.building_step(policy, snapshot, ARENA_BUILDING, family=FAMILY)
    if step is None:
        return None
    if not enters:
        return morivant_tower.approach_key(policy, snapshot, ARENA_BUILDING, step, APPROACH_REASON)
    policy.last_reason = reason
    key = policy._step_toward(snapshot, step, tail=tail)
    if key is not None and reason == POSTER_REASON:
        record.poster_posted = True
    return key


def _entry_key(policy, snapshot, record) -> str | None:
    """Telmora: read the poster, then enter."""
    if armor_smith.no_progress(record, snapshot):
        return _close(record)
    if not record.poster_checked:
        if not record.poster_posted:
            key = _building_key(policy, snapshot, record, POSTER_KEY + LEAVE_STORE_KEY, POSTER_REASON)
            return key if key is not None else _close(record)
        if not _poster_agrees(policy, snapshot, record.expected):
            return _close(record)
        record.poster_checked = True
    key = _building_key(policy, snapshot, record, ENTER_KEY, ENTER_REASON)
    return key if key is not None else _close(record)


def _return_key(policy, snapshot, record, town: int) -> str | None:
    if record.origin is None or record.origin == town:
        record.origin = None
        record.holding = record.returning = False
        return None
    record.holding = record.returning = True
    return _leg_key(policy, snapshot, record, record.origin, RETURN_REASON)


def trip_key(policy, snapshot) -> str | None:
    """While the trip is under way this owner holds the town's board.

    A fresh visit after a fight is not held: the town's processing starts over and the
    next recall read asks ``town_key`` again."""
    record = state(policy)
    if (not record.holding or record.closed
            or not armor_smith.board_allows(policy, snapshot)):
        return None
    town = policy._effective_town_id(snapshot)
    if record.returning:
        return _return_key(policy, snapshot, record, town)
    if over_for_good(policy):
        return _return_key(policy, snapshot, record, town)
    if town != TELMORA_TOWN_ID:
        return _leg_key(policy, snapshot, record, TELMORA_TOWN_ID, TRAVEL_REASON)
    return _entry_key(policy, snapshot, record)


def town_key(policy, snapshot) -> str | None:
    """At the recall read: the next key of the errand, or None for the read."""
    record = state(policy)
    if record.closed or not armor_smith.board_allows(policy, snapshot):
        return None
    town = policy._effective_town_id(snapshot)
    verdict = record.last_verdict = judge(policy, snapshot, record, town)
    if not verdict["go"]:
        return _return_key(policy, snapshot, record, town)
    record.expected = verdict["race_id"]
    if town == TELMORA_TOWN_ID:
        record.holding = True
        return _entry_key(policy, snapshot, record)
    if record.travelled:
        return None  # came back from Telmora with no fight: one trip in a stay
    key = _leg_key(policy, snapshot, record, TELMORA_TOWN_ID, TRAVEL_REASON)
    if key is not None:
        record.origin, record.holding, record.travelled = town, True, True
    return key


# --- The floor -----------------------------------------------------------------------


def _hostiles(snapshot) -> list:
    return [monster for monster in snapshot.visible_monsters if monster.hostile]


def _walk_toward(policy, snapshot, goal, reason: str) -> str:
    """One step that shortens the way to ``goal``; the arena is one open room."""
    here = snapshot.player.position
    if here.distance_to(goal) <= 1:
        policy.last_reason = reason
        return policy._step_toward(snapshot, goal)
    cells = [cell for cell in policy._walkable_neighbors(snapshot, here)
             if not (grid := snapshot.grid_at(cell)).has_monster and grid.building_type < 0]
    if not cells:
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    policy.last_reason = reason
    return policy._step_toward(snapshot, min(cells, key=lambda cell: (
        cell.distance_to(goal), abs(cell.y - goal.y) + abs(cell.x - goal.x), cell.y, cell.x)))


def _aligned(origin, cell) -> bool:
    dy, dx = abs(cell.y - origin.y), abs(cell.x - origin.x)
    return dy == 0 or dx == 0 or dy == dx


def _heal_key(policy, snapshot) -> str | None:
    """An absorbed Healing power above the owner's rate, below the walking gate's HP line
    (no potion works here)."""
    player = snapshot.player
    if (player.hp >= policy._low_hp_walk_threshold(player.max_hp) or player.blind
            or player.confused or player.hallucinated):
        return None
    for kind, sval, _amount, _success in arena_odds.healing_rows(policy):
        if me_capability.charges(policy, snapshot, kind, sval) > 0:
            policy.last_reason = HEAL_REASON
            return _power_key(kind, sval)
    return None


def _power_key(kind: str, sval: int) -> str:
    return "m" + me_powers.KIND_LETTER[kind] + me_powers.encode_letter(sval)


def _speed_key(policy, snapshot) -> str | None:
    """The Magic-Eater's haste, first and again when it ends (owner 「加速し」)."""
    player = snapshot.player
    if (not arena_odds.magic_eater(snapshot) or player.blind or player.confused
            or player.hallucinated or policy._player_hasted(snapshot)
            or not arena_odds.speed_held(policy, snapshot)):
        return None
    policy.last_reason = SPEED_REASON
    return _power_key("staff", SV_STAFF_SPEED)


def _power_attack_key(policy, snapshot, target) -> str | None:
    """The strongest absorbed attack: on a ray by its direction, else at the monster's cell
    (the room is open and lit, and a bolt stops at the first monster on its way)."""
    here = snapshot.player.position
    direction = policy._direction_key(here, target.position)
    ranked = me_device_attacks.scored(policy, snapshot, target, direction)
    if not ranked or ranked[0][0] <= 0:
        return None
    power = ranked[0][1]
    if not power.aimed or _aligned(here, target.position):
        return me_device_attacks.device_key(policy, power, direction)
    return me_device_attacks.device_target_key(policy, power, target.position)


def _shot_key(policy, snapshot, target) -> str | None:
    """The launcher, on any cell: beside the target too (cmd-shoot.cpp does not refuse)."""
    here = snapshot.player.position
    if here.distance_to(target.position) > 1:
        return policy._ranged_attack_key(snapshot, [target], [])
    chosen = policy._ranged_projectile(snapshot)
    if chosen is None:
        return None
    key = reserved_item_command(policy, snapshot, chosen[0], chosen[1],
                                suffix=policy._direction_key(here, target.position))
    if key is not None:
        policy.last_reason = chosen[2]
    return key


def _fired_key(policy, snapshot, target, ranged) -> str | None:
    """The strongest of ``ranged`` (arena_odds.ranged_force)."""
    if not ranged:
        return None
    if ranged[0][2] == "launcher":
        return _shot_key(policy, snapshot, target)
    return _power_attack_key(policy, snapshot, target)


def _away_key(policy, snapshot, target) -> str:
    """arena_fight_chain's STRIKE_OR_FIRE away from the target: fire, else a step.

    The owner's count (「直す」, 2026-11-05) holds only if the fight does what it counts."""
    key = _fired_key(policy, snapshot, target, arena_odds.ranged_force(policy, snapshot, target))
    return key if key is not None else _walk_toward(policy, snapshot, target.position, WALK_REASON)


def _fewest_actions_key(policy, snapshot, target) -> str | None:
    """The Magic-Eater: arena_fight_chain's FEWEST_ACTIONS; None is melee or the walk to it.

    Owner: 「近接攻撃によほど優れていなければ遠距離攻撃が評価の中心になる」: melee is charged the
    walk to reach it in the same count, and no other margin.  A ranged choice stays put."""
    here = snapshot.player.position
    ranged = arena_odds.ranged_force(policy, snapshot, target)
    melee = attack_expectation.melee(policy, snapshot, target)
    walk = max(0, here.distance_to(target.position) - 1)
    if not arena_fight_chain.melee_is_fewest(max(target.hp, 1), ranged, melee, walk):
        return _fired_key(policy, snapshot, target, ranged)
    return None


def _attack_key(policy, snapshot, target) -> str:
    here = snapshot.player.position
    is_magic_eater = arena_odds.magic_eater(snapshot)
    if is_magic_eater:
        key = _fewest_actions_key(policy, snapshot, target)
        if key is not None:
            return key
    if here.distance_to(target.position) <= 1:
        answer = combat_answer.adjacent_attack(policy, snapshot, [target], MELEE_REASON)
        if answer is not None:
            return answer.key
        policy.last_reason = HOLD_REASON  # afraid with nothing to shoot: no way out of here
        return WAIT_KEY
    if is_magic_eater:
        return _walk_toward(policy, snapshot, target.position, WALK_REASON)
    knowledge = policy._monrace_knowledge.get(target.race_id)
    if knowledge is not None and arena_fight_chain.applies(knowledge):
        return _away_key(policy, snapshot, target)
    if _aligned(here, target.position):
        key = me_ranged_first.attack_key(policy, snapshot, target)
        if key is not None:
            return key
    melee = attack_expectation.melee(policy, snapshot, target)
    shot = policy._estimated_ranged_damage_per_shot(snapshot)
    if shot >= melee:
        key = policy._ranged_attack_key(snapshot, [target], [])
        if key is not None:
            return key
    return _walk_toward(policy, snapshot, target.position, WALK_REASON)


def _unseen_key(policy, snapshot) -> str | None:
    """Blind, hallucinating, or a monster the gate says is alive: strike, else hold."""
    key = blind_strike.strike_key(policy, snapshot, BLIND_STRIKE_REASON)
    if key is not None:
        return key
    if unseen_strike.hit_in_melee(policy, snapshot):
        key = unseen_strike.key(policy, snapshot, [], STRIKE_REASON)
        if key is not None:
            return key
    policy.last_reason = HOLD_REASON
    return WAIT_KEY


def _won_key(policy, snapshot, record) -> str:
    """No monster in view on a lit floor: the reward, then the gate."""
    here = snapshot.player.position
    grid_here = snapshot.grid_at(here)
    if (grid_here is not None and grid_here.object_count > 0
            and here not in record.tried_reward_cells):
        record.tried_reward_cells.add(here)
        policy.last_reason = PICKUP_REASON
        return PICKUP_KEY + ("a" * grid_here.object_count if grid_here.object_count > 1 else "")
    rewards = [cell for cell, grid in snapshot.grids.items()
               if grid.object_count > 0 and cell not in record.tried_reward_cells]
    if rewards:
        goal = min(rewards, key=lambda cell: (here.distance_to(cell), cell.y, cell.x))
        return _walk_toward(policy, snapshot, goal, REWARD_REASON)
    gate = next((cell for cell, grid in snapshot.grids.items()
                 if grid.building_type == ARENA_BUILDING), None)
    if gate is None:
        policy.last_reason = HOLD_REASON
        return WAIT_KEY
    if here == gate:
        record.gate_attempts += 1  # a step onto it left the floor unless it is shut
        cells = policy._walkable_neighbors(snapshot, here)
        if cells:
            policy.last_reason = GATE_REASON
            return policy._step_toward(snapshot, cells[0])
    return _walk_toward(policy, snapshot, gate, GATE_REASON)


def fight_key(policy, snapshot) -> str:
    """The one owner of this floor: there is no way out before the end, so it never asks
    the survival rungs, whose scrolls and potions the game refuses.  A fight that can no
    longer be won goes on: a loss here costs nothing but the arena."""
    policy._build_grid_index(snapshot)
    record = state(policy)
    player = snapshot.player
    heal = _heal_key(policy, snapshot)
    if heal is not None:
        return heal
    hostiles = _hostiles(snapshot)
    if hostiles:
        here = player.position
        speed = _speed_key(policy, snapshot)
        if speed is not None:
            return speed
        target = min(hostiles, key=lambda monster: (here.distance_to(monster.position), monster.index))
        return _attack_key(policy, snapshot, target)
    if (player.blind or player.hallucinated or snapshot.detected_monsters
            or record.gate_attempts >= GATE_ATTEMPTS):
        return _unseen_key(policy, snapshot)
    return _won_key(policy, snapshot, record)
