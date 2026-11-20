"""The Magic-Eater's way to Angband 99F and 100F: readiness, supplies and the cap's lift.

Owner 2026-11-20 (verbatim, the 99F/100F directive):
「99Fと100Fの戦闘方針を作る。
99F/100Fに降りる前に常に小さめのフロアを選択するオプションを有効にする。
…
帰還による離脱は成功時と魔力復活の薬を予定の倍以上使ったときのみ。
装備は加速耐性テレパシーー知力耐久力を優先。ACや近接攻撃力は求めない。
体力回復の薬、*体力回復*の薬、耐性の薬、魔力復活の薬、テレポートの巻物を大量に持つ。減速後加速+25を超えて
いれば重量過多を許可する。」
and the answers to its questions (2026-11-20):
1. 「準備ができるまで鉄獄95Fで探索」 ends (angband_cap) when, on a town board, the Restore Mana reaches
   its computed target (restore_mana_target), the five supplies their counts and the equipment its
   conditions (speed, the resistances, telepathy); until then 95F is explored as before.
2. The counts: Healing 30, *Healing* 15, Resistance 20, Teleportation 40, Restore Mana the
   computed target (「予定」 of the recall rule is that target: recall once 2x it is used).
3. 「+25」: the permanent speed (gear and innate, no potion and no absorbed Speed) after the weight's
   slowdown must exceed +25 for the pack to be over the weight limit.
Added 2026-11-20 (verbatim): 「呪力耐性も要求する。これはオベロンの血の呪い、サーペントの破滅の手が
致死的であるためである。」 -- resist curse (TR_RES_CURSE, the board's ``resist_curse``) is an
equipment condition of the readiness and of the dedicated loadout (equipment_optimizer ``finale``).
The answers to the report's questions (2026-11-20, verbatim):
* Q6 「耐盲目か耐閃光を条件に入れる」: *Destruction*'s flash blinds without either
  (spells-floor.cpp:416), and a blind player reads no Teleportation; an equipment condition too.
* Q7 「取り込んだ岩石溶解を条件に入れる」: the absorbed Stone to Mud, ``STONE_TO_MUD_COUNT``
  absorbed (bought and absorbed while the 95F exploration lasts, me_device_policy).
* Q9 「準備がそろってから」: the dedicated loadout, the carry and the weight allowance hold only
  once the character is ready; the readiness asks whether the gear owned (worn, carried, at Home)
  makes the equipment conditions, not only what is worn.

The readiness has two stages, both measured on every town board:
* ``supplied``: the supplies in the pack and at Home (the last Home census) and the absorbed
  Stone to Mud.  From here the optimizer orders the loadouts by the finale's rank (the owned set
  it chooses is the equipment the next stage judges).
* ``equipped`` (``Memory.stocked``): ``supplied`` and the equipment conditions met by the board's
  own abilities or by that chosen set.  From here the supplies are carried (kept, taken from
  Home), the pack may be overweight, and the optimizer's swap to the set is the town's work.
* ``ready`` (``Memory.ready``, the cap's lift): ``equipped`` with the counts in the pack and the
  conditions on the board itself (the set worn).

Who reads what here:

* ``observe`` (every decision): on a town board the readiness is measured again and latched
  (``Memory.ready``); a dungeon board keeps the latch of the town it left, so the dive the town
  decided is the dive taken.  The restore-mana uses of the expedition are counted on the dungeon
  boards (a drop of the carried potions on 99F/100F) and cleared in town.
* ``lifted``: angband_cap's lift (``cap(..., policy)``): no 95F cap while the latch holds.
* ``carry_target`` / ``retention`` / ``potion_target`` / ``missing``: the supply plan once the
  character prepares (a Magic-Eater whose Angband recall depth reached the cap): what the pack
  keeps (policy_home), takes from Home and buys (policy_supply, policy_shop).
* ``weight_limit``: the pack's limit under answer 3 (policy_home ``_inventory_overweight``).
* ``small_floor_key``: the gameplay option always_small_floor (option-types-table.cpp:199,
  floor-info.cpp:1116) set with the pref command ``"`` (cmd-dump.cpp do_cmd_pref,
  interpret-pref-file.cpp ``Y:<option>``: a GAMEPLAY option, no game time) before the descent.

The battle on the floors themselves is angband_finale_battle.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hengbot import restore_mana_target
from hengbot.model import (
    DUNGEON_ANGBAND, SV_POTION_HEALING, SV_POTION_RESISTANCE, SV_POTION_RESTORE_MANA,
    SV_POTION_STAR_HEALING, SV_SCROLL_TELEPORT, TVAL_POTION, TVAL_SCROLL,
)

PLAYER_CLASS_MAGIC_EATER = 16
# The floor the 95F exploration happens on (angband_cap.ANGBAND_DEPTH_CAP): a character whose
# Angband recall depth reached it prepares the finale.
PREPARE_DEPTH = 95
# lib/edit/quests 008_Oberon.jsonc (KILL_LEVEL 99, monster 860) and 009_SerpentOfChaos.jsonc
# (level 100, monster 862): depth -> (quest id, target race).
FINALE = {99: (8, 860), 100: (9, 862)}
FINALE_DEPTHS = tuple(sorted(FINALE))

HEALING = (TVAL_POTION, SV_POTION_HEALING)
STAR_HEALING = (TVAL_POTION, SV_POTION_STAR_HEALING)
RESISTANCE = (TVAL_POTION, SV_POTION_RESISTANCE)
TELEPORT = (TVAL_SCROLL, SV_SCROLL_TELEPORT)
RESTORE_MANA = (TVAL_POTION, SV_POTION_RESTORE_MANA)
# Owner 2026-11-20 answer 2.
CARRY = {HEALING: 30, STAR_HEALING: 15, RESISTANCE: 20, TELEPORT: 40}
SUPPLY_NAMES = {HEALING: "healing", STAR_HEALING: "star_healing", RESISTANCE: "resistance",
                TELEPORT: "teleport", RESTORE_MANA: "restore_mana"}
RESIST_CURSE = "resist_curse"  # bot-json-output.cpp, TR_RES_CURSE
# Owner 2026-11-20 Q6: either one keeps *Destruction*'s flash from blinding.
BLIND_OR_LITE = ("resist_blind", "resist_lite")
# Owner 2026-11-20 Q7 「取り込んだ岩石溶解を条件に入れる」: the absorbed count (the uses one full list
# holds).  Ten: a stand's line crosses the walls between two rooms of a small floor, one to five
# of them (the battle's test stand melts five), and the battle stands again after each teleport;
# ten holds two such lines, and from ten absorbed a Restore Mana refills count / 3 = 3+ uses
# (spells-status.cpp restore_mana) instead of the fixed 3 below it.
STONE_TO_MUD = ("wand", 6)
STONE_TO_MUD_COUNT = 10
# The board's lasting ability sources other than the gear (race, class, personality).
INTRINSIC_SOURCES = frozenset({"permanent"})
# Owner 2026-11-20 answer 3: 「+25を超えていれば」 over the base speed 110.
OVERWEIGHT_SPEED_OVER = 25
BASE_SPEED = 110
# Owner 2026-11-20 「魔力復活の薬を予定の倍以上使ったとき」.
RESTORE_MANA_RECALL_SHARE = 2
# The pref command that sets the option (interpret-pref-file.cpp interpret_xy_token).
SMALL_FLOOR_PREF = "Y:always_small_floor"
SMALL_FLOOR_MACRO = '"' + SMALL_FLOOR_PREF + "\r"
SMALL_FLOOR_REASON = "angband-finale:small-floor"
RETENTION_BRANCH = "angband-finale:carry"
CATEGORY = "angband-finale"  # the town need of the Teleportation stock

MEMORY = "_angband_finale"
# policy_constants QUEST_STATUS_COMPLETED, REWARDED, FINISHED: the target was killed.
DONE_STATUSES = frozenset({2, 3, 4})


@dataclass
class Memory:
    ready: bool = False               # the last town board's readiness (the cap's lift)
    supplied: bool = False            # the supplies owned (pack + Home) and the Stone to Mud
    stocked: bool = False             # supplied and the equipment owned: carry, weight, loadout
    report: dict = field(default_factory=dict)  # that board's rows, for the record
    small_floor_set: bool = False     # the pref command was answered by the game
    small_floor_pending: int | None = None  # the turn of the posted command
    restore_mana_used: int = 0        # this expedition's Restore Mana spent on 99F/100F
    restore_mana_seen: int | None = None    # the carried count on the last dungeon board


def memory(policy) -> Memory:
    held = getattr(policy, MEMORY, None)
    if held is None:
        held = Memory()
        setattr(policy, MEMORY, held)
    return held


def magic_eater(snapshot) -> bool:
    return snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER


def _kind(item) -> tuple[int, int]:
    return item.tval, item.sval


def carried(snapshot, kind) -> int:
    """The aware ``kind`` the pack holds."""
    return sum(item.count for item in snapshot.inventory
               if _kind(item) == kind and getattr(item, "aware", True))


def owned(policy, snapshot, kind) -> int:
    """The pack's and the last Home census's ``kind``."""
    home = getattr(policy, "_home_knowledge_items", ()) or ()
    return carried(snapshot, kind) + sum(item.count for item in home
                                         if _kind(item) == kind and getattr(item, "aware", True))


def angband_depth(snapshot) -> int:
    """The Angband recall depth (the save's max level there), or the floor stood on."""
    depth = int((getattr(snapshot, "dungeon_recall_depths", None) or {}).get(DUNGEON_ANGBAND, 0) or 0)
    if not snapshot.in_town and snapshot.floor_key[0] == DUNGEON_ANGBAND:
        depth = max(depth, snapshot.dungeon_level)
    return depth


def preparing(snapshot) -> bool:
    """A Magic-Eater whose Angband recall depth reached the 95F exploration: the supply plan and
    the dedicated loadout hold from here on."""
    return magic_eater(snapshot) and angband_depth(snapshot) >= PREPARE_DEPTH


def restore_mana_goal(policy, snapshot) -> int | None:
    """restore_mana_target's computed target (None until a rocket is absorbed)."""
    figures = restore_mana_target.plan(policy, snapshot)
    return None if figures is None else figures["target"]


def _row(measured: int, required: int | None) -> dict:
    return {"measured": measured, "required": required,
            "ready": required is not None and measured >= required}


def supply_rows(policy, snapshot, count) -> dict:
    """The supplies counted by ``count`` (``carried`` or ``owned``) and the absorbed Stone to
    Mud (owner 2026-11-20 Q7), each ``{measured, required, ready}``."""
    from hengbot import me_capability
    rows = {SUPPLY_NAMES[RESTORE_MANA]: _row(count(RESTORE_MANA), restore_mana_goal(policy, snapshot))}
    for kind, target in CARRY.items():
        rows[SUPPLY_NAMES[kind]] = _row(count(kind), target)
    rows["stone_to_mud"] = _row(me_capability.count(policy, snapshot, *STONE_TO_MUD),
                                STONE_TO_MUD_COUNT)
    return rows


def _board_abilities(snapshot) -> frozenset:
    from hengbot import amberite_curse  # import cycle
    abilities = set(snapshot.player.abilities)
    if amberite_curse.resists_curse(snapshot):
        abilities.add(RESIST_CURSE)  # read as the Amberite rule reads it
    else:
        abilities.discard(RESIST_CURSE)
    return frozenset(abilities)


def _missing(policy, snapshot, abilities, *, speed_met: bool, means_held: bool) -> list:
    from hengbot.policy_constants import (DESTRUCTION_GATE_LABEL, SPEED_GATE_LABEL,
                                          required_depth_gates)
    missing = set(required_depth_gates(FINALE_DEPTHS[0])) - set(abilities)
    missing.discard(SPEED_GATE_LABEL)
    missing.discard(DESTRUCTION_GATE_LABEL)
    if not speed_met:
        missing.add(SPEED_GATE_LABEL)
    if not means_held:
        missing.add(DESTRUCTION_GATE_LABEL)
    if RESIST_CURSE not in abilities:
        missing.add(RESIST_CURSE)
    if not any(name in abilities for name in BLIND_OR_LITE):
        missing.add("|".join(BLIND_OR_LITE))
    return sorted(missing)


def board_missing(policy, snapshot) -> list:
    """The equipment conditions the board itself does not meet (the gear worn)."""
    worn = policy._missing_required_abilities(snapshot, FINALE_DEPTHS[0])
    from hengbot.policy_constants import DESTRUCTION_GATE_LABEL, SPEED_GATE_LABEL
    return _missing(policy, snapshot, _board_abilities(snapshot) - set(worn),
                    speed_met=SPEED_GATE_LABEL not in worn,
                    means_held=DESTRUCTION_GATE_LABEL not in worn)


def owned_missing(policy, snapshot) -> list | None:
    """The equipment conditions the set the optimizer chose from the owned gear does not meet
    (owner 2026-11-20 Q9 「現在の装備と自宅の品で満たせるか」), else None (no chosen set yet)."""
    from hengbot.equipment_optimizer import ABILITY_FLAG
    from hengbot.speed_valuation import loadout_speed, meets_speed_gate
    preparation = getattr(policy, "_equipment_optimization_preparation", None)
    best = getattr(getattr(preparation, "result", None), "best", None)
    if best is None:
        return None
    flags = best.loadout.flags
    names = {**ABILITY_FLAG, RESIST_CURSE: 148, "resist_blind": 56, "resist_lite": 54}
    abilities = {name for name, flag in names.items() if flag in flags}
    abilities |= {name for name, sources in snapshot.player.ability_sources.items()
                  if set(sources) & INTRINSIC_SOURCES}
    from hengbot import destruction_use
    return _missing(policy, snapshot, frozenset(abilities),
                    speed_met=meets_speed_gate(loadout_speed(best.metrics)),
                    means_held=destruction_use.holds_means(policy, snapshot))


def readiness(policy, snapshot) -> dict:
    """The owner's conditions on this board: ``owned`` and ``carried`` supply rows, the
    equipment owned (``owned_missing``, else the board's) and worn (``board_missing``)."""
    worn = board_missing(policy, snapshot)
    chosen = owned_missing(policy, snapshot)
    owned_gear = worn if chosen is None or not worn else chosen
    return {"owned": supply_rows(policy, snapshot, lambda kind: owned(policy, snapshot, kind)),
            "carried": supply_rows(policy, snapshot, lambda kind: carried(snapshot, kind)),
            "equipment_owned": {"missing": owned_gear, "ready": not owned_gear},
            "equipment_worn": {"missing": worn, "ready": not worn}}


def ready(rows: dict) -> bool:
    return bool(rows) and all(row["ready"] for row in rows.values())


def observe(policy, snapshot) -> None:
    """Latch the readiness's stages on a town board; count the expedition's Restore Mana uses."""
    held = memory(policy)
    if held.small_floor_pending is not None and snapshot.turn is not None:
        # The pref command spends no game time: the next board after it is its answer.
        held.small_floor_set = True
        held.small_floor_pending = None
    if snapshot.in_town:
        held.restore_mana_used = 0
        held.restore_mana_seen = None
        if not preparing(snapshot):
            held.ready = held.supplied = held.stocked = False
            held.report = {}
            return
        held.report = rows = readiness(policy, snapshot)
        held.supplied = ready(rows["owned"])
        held.stocked = held.supplied and rows["equipment_owned"]["ready"]
        held.ready = (held.stocked and ready(rows["carried"])
                      and rows["equipment_worn"]["ready"])
        return
    now = carried(snapshot, RESTORE_MANA)
    if (held.restore_mana_seen is not None and now < held.restore_mana_seen
            and on_finale_floor(snapshot)):
        held.restore_mana_used += held.restore_mana_seen - now
    held.restore_mana_seen = now


def supplied(policy) -> bool:
    """The supplies are owned: the dedicated loadout's order holds (equipment_optimizer)."""
    held = getattr(policy, MEMORY, None)
    return bool(held is not None and held.supplied)


def stocked(policy) -> bool:
    """The supplies and the equipment are owned: the carry and the weight allowance hold."""
    held = getattr(policy, MEMORY, None)
    return bool(held is not None and held.stocked)


def lifted(policy) -> bool:
    """The 95F cap is lifted: the last town board was ready (owner 2026-11-20 answer 1)."""
    held = getattr(policy, MEMORY, None)
    return bool(held is not None and held.ready)


def on_finale_floor(snapshot) -> bool:
    """Angband 99F or 100F (the KILL_LEVEL floors; the floor's own quest_id is 0 there)."""
    return (not snapshot.in_town and snapshot.floor_key[0] == DUNGEON_ANGBAND
            and snapshot.dungeon_level in FINALE)


def target_race(snapshot) -> int | None:
    entry = FINALE.get(snapshot.dungeon_level) if on_finale_floor(snapshot) else None
    return None if entry is None else entry[1]


def quest_done(snapshot) -> bool:
    """This floor's quest is no longer TAKEN (killed: COMPLETED and later)."""
    entry = FINALE.get(snapshot.dungeon_level)
    if entry is None:
        return False
    quest = snapshot.quests.get(entry[0])
    return quest is not None and quest.status in DONE_STATUSES


def restore_mana_overspent(policy, snapshot) -> bool:
    """Owner 2026-11-20 「魔力復活の薬を予定の倍以上使ったとき」: the expedition used at least twice
    the computed target."""
    goal = restore_mana_goal(policy, snapshot)
    return goal is not None and memory(policy).restore_mana_used >= RESTORE_MANA_RECALL_SHARE * goal


# -- the supplies ------------------------------------------------------------------

def carry_target(policy, snapshot, item) -> int | None:
    """The finale's carry of ``item``'s kind once the supplies and the equipment are owned
    (owner 2026-11-20 Q9 「準備がそろってから」), else None."""
    if not preparing(snapshot) or not stocked(policy) or not getattr(item, "aware", True):
        return None
    kind = _kind(item)
    if kind == RESTORE_MANA:
        return restore_mana_goal(policy, snapshot)
    return CARRY.get(kind)


def shortage(policy, snapshot, kind) -> int:
    """What the purchases still owe the count of ``kind``: the stock owned (pack and Home) while
    the character prepares."""
    if not preparing(snapshot):
        return 0
    target = restore_mana_goal(policy, snapshot) if kind == RESTORE_MANA else CARRY.get(kind)
    return max(0, (target or 0) - owned(policy, snapshot, kind))


def retention(policy, snapshot, item) -> int | None:
    """The part of this pack stack the finale's carry keeps (allocated in pack order, so
    duplicate stacks share one target), else None."""
    target = carry_target(policy, snapshot, item)
    if target is None or not target:
        return None
    before = 0
    for stack in snapshot.inventory:
        if stack is item or stack.slot == item.slot:
            break
        if _kind(stack) == _kind(item) and getattr(stack, "aware", True):
            before += stack.count
    return min(item.count, max(0, target - before))


def potion_target(policy, snapshot, item) -> tuple[int, str] | None:
    """policy_supply ``_carry_strategy_potion_target``'s answer for the finale's potions."""
    if item.tval != TVAL_POTION:
        return None
    target = carry_target(policy, snapshot, item)
    return (target, RETENTION_BRANCH) if target else None


def missing(policy, snapshot, item) -> int | None:
    """policy_supply ``_procurement_missing_amount``'s answer for a Teleportation scroll (the
    potions answer through ``potion_target``), else None."""
    if _kind(item) != TELEPORT or not preparing(snapshot) or not stocked(policy):
        return None
    return max(0, CARRY[TELEPORT] - carried(snapshot, TELEPORT))


def stone_to_mud_wanted(policy, snapshot, row) -> bool:
    """Another Stone to Mud wand bought while the 95F exploration lasts and fewer than
    ``STONE_TO_MUD_COUNT`` are absorbed (owner 2026-11-20 Q7); me_device_policy absorbs it."""
    from hengbot import me_capability
    from hengbot.model import TVAL_WAND
    return ((row.tval, row.sval) == (TVAL_WAND, STONE_TO_MUD[1])
            and preparing(snapshot)
            and me_capability.count(policy, snapshot, *STONE_TO_MUD) < STONE_TO_MUD_COUNT)


def black_market_wanted(policy, snapshot, item) -> bool:
    """A Black Market *Healing* toward the carry (the table buys none otherwise)."""
    return _kind(item) == STAR_HEALING and shortage(policy, snapshot, STAR_HEALING) > 0


# -- the weight ---------------------------------------------------------------------

def slowdown(weight: int, limit: int) -> int:
    """player-speed.cpp calc_speed_bonus_by_weight: (weight - limit) / (limit / 5) over it."""
    if weight <= limit or limit < 5:
        return 0
    return (weight - limit) // (limit // 5)


def weight_limit(policy, snapshot, limit: int | None) -> int | None:
    """The heaviest pack answer 3 allows once the supplies and the equipment are owned (owner
    2026-11-20 Q9): the weight whose slowdown keeps the permanent speed above +25 (``limit``
    itself when none does)."""
    if limit is None or not preparing(snapshot) or not stocked(policy):
        return limit
    from hengbot.speed_valuation import permanent_player_speed
    unslowed = permanent_player_speed(snapshot) + slowdown(policy._inventory_weight(snapshot), limit)
    # The slowdown steps that keep the speed above +25 (at least +26).
    spare = unslowed - (BASE_SPEED + OVERWEIGHT_SPEED_OVER) - 1
    if spare < 0:
        return limit
    # slowdown(weight) <= spare up to the last weight below the next step.
    return limit + (spare + 1) * (limit // 5) - 1


# -- the option ------------------------------------------------------------------------

def small_floor_due(policy, snapshot) -> bool:
    """The cap is lifted and the option was not set yet this life: before the descent."""
    held = getattr(policy, MEMORY, None)
    return bool(held is not None and held.ready and not held.small_floor_set
                and held.small_floor_pending is None and magic_eater(snapshot))


def small_floor_key(policy, snapshot) -> str | None:
    """``"Y:always_small_floor`` + Enter (no game time), else None."""
    if not small_floor_due(policy, snapshot):
        return None
    if not snapshot.in_town and snapshot.floor_key[0] == DUNGEON_ANGBAND \
            and snapshot.dungeon_level >= FINALE_DEPTHS[0]:
        return None  # already down: only before the descent
    memory(policy).small_floor_pending = snapshot.turn
    policy.last_reason = SMALL_FLOOR_REASON
    return SMALL_FLOOR_MACRO


def describe(policy) -> dict | None:
    held = getattr(policy, MEMORY, None)
    if held is None:
        return None
    return {"ready": held.ready, "supplied": held.supplied, "stocked": held.stocked,
            "report": held.report, "small_floor_set": held.small_floor_set,
            "restore_mana_used": held.restore_mana_used}
