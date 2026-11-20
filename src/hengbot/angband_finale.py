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


def readiness(policy, snapshot) -> dict:
    """Answer 1's conditions on this board, each ``{measured, required, ready}``.

    The supplies are counted in the pack (what the dive takes; Home stock is taken out first by
    ``potion_target`` / ``missing``); the equipment conditions are the depth table's for 99F
    (policy ``_missing_required_abilities``: speed +25, the resistances, telepathy, the
    *Destruction* means) and resist curse (owner 2026-11-20)."""
    rows = {SUPPLY_NAMES[RESTORE_MANA]: _row(carried(snapshot, RESTORE_MANA),
                                             restore_mana_goal(policy, snapshot))}
    for kind, count in CARRY.items():
        rows[SUPPLY_NAMES[kind]] = _row(carried(snapshot, kind), count)
    missing = sorted(policy._missing_required_abilities(snapshot, FINALE_DEPTHS[0]))
    rows["equipment"] = {"missing": missing, "ready": not missing}
    # The board's reading of resist curse the Amberite rule reads (amberite_curse.resists_curse).
    from hengbot import amberite_curse  # import cycle
    rows[RESIST_CURSE] = {"ready": amberite_curse.resists_curse(snapshot)}
    return rows


def ready(rows: dict) -> bool:
    return bool(rows) and all(row["ready"] for row in rows.values())


def observe(policy, snapshot) -> None:
    """Latch the readiness on a town board; count the expedition's Restore Mana uses."""
    held = memory(policy)
    if held.small_floor_pending is not None and snapshot.turn is not None:
        # The pref command spends no game time: the next board after it is its answer.
        held.small_floor_set = True
        held.small_floor_pending = None
    if snapshot.in_town:
        held.restore_mana_used = 0
        held.restore_mana_seen = None
        if not preparing(snapshot):
            held.ready, held.report = False, {}
            return
        held.report = readiness(policy, snapshot)
        held.ready = ready(held.report)
        return
    now = carried(snapshot, RESTORE_MANA)
    if (held.restore_mana_seen is not None and now < held.restore_mana_seen
            and on_finale_floor(snapshot)):
        held.restore_mana_used += held.restore_mana_seen - now
    held.restore_mana_seen = now


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
    """The finale's carry of ``item``'s kind while the character prepares, else None."""
    if not preparing(snapshot) or not getattr(item, "aware", True):
        return None
    kind = _kind(item)
    if kind == RESTORE_MANA:
        return restore_mana_goal(policy, snapshot)
    return CARRY.get(kind)


def shortage(policy, snapshot, kind) -> int:
    if not preparing(snapshot):
        return 0
    target = restore_mana_goal(policy, snapshot) if kind == RESTORE_MANA else CARRY.get(kind)
    return max(0, (target or 0) - carried(snapshot, kind))


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
    if _kind(item) != TELEPORT or not preparing(snapshot):
        return None
    return shortage(policy, snapshot, TELEPORT)


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
    """The heaviest pack answer 3 allows: while preparing, the weight whose slowdown keeps the
    permanent speed above +25 (``limit`` itself when none does)."""
    if limit is None or not preparing(snapshot):
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
    return {"ready": held.ready, "report": held.report, "small_floor_set": held.small_floor_set,
            "restore_mana_used": held.restore_mana_used}
