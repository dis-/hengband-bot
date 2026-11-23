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
  makes the equipment conditions, not only what is worn.  And (verbatim) 「上限を外す時に初めて
  着け替える」: the 95F exploration keeps the ordinary loadout and weight rules the whole time;
  the switch is the town visit that heads to 99F/100F, and the cap lifts after it.

The switch itself is the preparation phase (finale_prep, owner 2026-11-21 「専用の準備フェイズを作って
準備して」): its check, supplies, loadout, swap and recall steps own the transition, and the readers
below ask it (``carrying``, ``lifted``).

Who reads what here:

* ``observe`` (every decision): on a town board the readiness is measured (``supplied``: the
  supplies in the pack and at Home, the last Home census, and the absorbed Stone to Mud) and
  handed to the phase.  The restore-mana uses of the expedition are counted on the dungeon boards
  (a drop of the carried potions on 99F/100F) and cleared in town.
* ``lifted``: angband_cap's lift (``cap(..., policy)``): the phase's recall step and the expedition.
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

from hengbot import ability_sources
from hengbot import restore_mana_target
from hengbot.model import (
    DUNGEON_ANGBAND, SV_POTION_HEALING, SV_POTION_RESISTANCE, SV_POTION_RESTORE_MANA,
    SV_POTION_STAR_HEALING, SV_SCROLL_TELEPORT, TVAL_FOOD, TVAL_POTION, TVAL_SCROLL,
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
# Owner 2026-11-21 「99F100Fに全復活のキノコをあるだけ持っていく」: every Mushroom of Restoring owned
# (sv-food-types.h SV_FOOD_RESTORING; cmd-eat.cpp restore_all_status), no count and no condition.
RESTORING = (TVAL_FOOD, 19)
RESTORING_CARRY = 99  # 「あるだけ」: every one (a stack's limit)
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
    supplied: bool = False            # the supplies owned (pack + Home) and the Stone to Mud
    report: dict = field(default_factory=dict)  # that board's rows, for the record
    small_floor_set: bool = False     # the pref command was answered by the game
    small_floor_pending: int | None = None  # the turn of the posted command
    restore_mana_used: int = 0        # this expedition's Restore Mana spent on 99F/100F
    restore_mana_seen: int | None = None    # the carried count on the last dungeon board
    in_town: bool | None = None       # the last board's side
    # The last current Home census's counts of the finale's kinds ({(tval, sval): count}), kept
    # across the trip: the Home does not change while the character is away, and the arrival
    # board often has no census (n1-c life-217 2026-11-20 23:30:21: none until the visit's
    # second board, so the Home's 120 Restore Mana were not counted).  None: none seen yet.
    home_counts: dict | None = None
    # The other towns' Teleportation circuit (finale_teleport_tour) ended on this trip: no new
    # one until a dungeon board.  A class default: restored checkpoints predate it.
    teleport_tour_done: bool = False
    # The owned gear's best set in the finale's rank (equipment_optimizer EvaluatedLoadout), from
    # the read-only search policy_equipment runs once a town visit while the character prepares
    # (``owned_report_due``), kept across the trip; the readiness's ``equipment_owned`` reads it
    # (n1-c life-221 2026-11-23: with the phase idle no search ran and the report showed the worn
    # set's resist curse and blindness missing, ★賢者マーリンの魔法の鏡 at Home).  Class defaults:
    # restored checkpoints predate them.
    owned_best: object | None = None
    owned_searched: bool = False      # searched on this town visit


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


def _census_current(policy) -> bool:
    return bool(getattr(policy, "_home_knowledge_current", False)
                and getattr(policy, "_home_knowledge_items", ()))


def home_count(policy, kind) -> int | None:
    """The Home's ``kind``: the current census, else the last one kept across the trip
    (``Memory.home_counts``), else None (no census seen)."""
    if _census_current(policy):
        return sum(item.count for item in policy._home_knowledge_items
                   if _kind(item) == kind and getattr(item, "aware", True))
    held = getattr(policy, MEMORY, None)
    counts = getattr(held, "home_counts", None)
    return None if counts is None else counts.get(kind, 0)


def owned(policy, snapshot, kind) -> int:
    """The pack's and the Home's ``kind`` (``home_count``; nothing counted without a census)."""
    return carried(snapshot, kind) + (home_count(policy, kind) or 0)


def _keep_home_counts(policy) -> None:
    """Remember the current census's counts of the finale's kinds for the next arrival."""
    if _census_current(policy):
        memory(policy).home_counts = {kind: home_count(policy, kind)
                                      for kind in (*CARRY, RESTORE_MANA)}


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
    """restore_mana_target's computed target, "the plan" (None until a rocket is absorbed)."""
    figures = restore_mana_target.plan(policy, snapshot)
    return None if figures is None else figures["target"]


def restore_mana_carry(policy, snapshot) -> int | None:
    """What the expeditions own and carry: twice the plan (restore_mana_target.CARRY_FACTOR,
    owner 2026-11-21 「想定の倍にして」「99Fも想定の倍で」)."""
    figures = restore_mana_target.plan(policy, snapshot)
    return None if figures is None else figures["carry"]


def _row(measured: int, required: int | None) -> dict:
    return {"measured": measured, "required": required,
            "ready": required is not None and measured >= required}


def supply_rows(policy, snapshot, count) -> dict:
    """The supplies counted by ``count`` (``carried`` or ``owned``) and the absorbed Stone to
    Mud (owner 2026-11-20 Q7), each ``{measured, required, ready}``."""
    from hengbot import me_capability
    rows = {SUPPLY_NAMES[RESTORE_MANA]: _row(count(RESTORE_MANA), restore_mana_carry(policy, snapshot))}
    for kind, target in CARRY.items():
        rows[SUPPLY_NAMES[kind]] = _row(count(kind), target)
    rows["stone_to_mud"] = _row(me_capability.count(policy, snapshot, *STONE_TO_MUD),
                                STONE_TO_MUD_COUNT)
    return rows


def _board_abilities(snapshot) -> frozenset:
    from hengbot import amberite_curse  # import cycle
    abilities = set(ability_sources.held_abilities(snapshot.player))
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
    """The equipment conditions the set the read-only search chose from the owned gear does not
    meet (owner 2026-11-20 Q9 「現在の装備と自宅の品で満たせるか」): finale_prep's check step's search,
    else the visit's search kept for the report (``owned_best``), else None (no chosen set)."""
    from hengbot import finale_prep
    best = getattr(getattr(getattr(policy, "_angband_finale_feasibility", None), "result", None),
                   "best", None)
    if best is None:
        best = getattr(getattr(policy, MEMORY, None), "owned_best", None)
    if best is None:
        return None
    return finale_prep.set_missing(policy, snapshot, best.loadout, best.metrics)


def owned_report_due(policy, snapshot, catalog) -> bool:
    """policy_equipment's read-only search over the owned gear in the finale's rank, for the
    report (``owned_best``): in town while the character prepares, once a visit, again when a
    piece of the kept set is no longer owned (``catalog``: the search's owned pieces).  Not while
    the worn loadout's own search is in the finale's rank (``keep_owned_best`` takes its set) nor
    in the check step (its own search)."""
    from hengbot import finale_prep  # import cycle
    if (not snapshot.in_town or not preparing(snapshot) or finale_prep.dedicated_order(policy)
            or finale_prep.owned_search_due(policy)):
        return False
    held = memory(policy)
    if not held.owned_searched or held.owned_best is None:
        return True
    owned_now = {finale_prep._signature(owned.id) for owned in catalog}
    return any(finale_prep._signature(item.id) not in owned_now
               for _, item in held.owned_best.loadout.slots)


def keep_owned_best(policy, snapshot, preparation) -> None:
    """Keep the set a search in the finale's rank chose from the owned gear (the report's
    ``owned_best``); a search that chose none (a blocked or incomplete one) keeps the old one."""
    best = getattr(getattr(preparation, "result", None), "best", None)
    if best is None or not snapshot.in_town:
        return
    held = memory(policy)
    held.owned_best, held.owned_searched = best, True


def readiness(policy, snapshot) -> dict:
    """The owner's conditions on this board: ``owned`` and ``carried`` supply rows, the
    equipment owned (``owned_missing``, else the board's) and worn (``board_missing``)."""
    worn = board_missing(policy, snapshot)
    chosen = owned_missing(policy, snapshot)
    owned_gear = worn if chosen is None else chosen
    return {"owned": supply_rows(policy, snapshot, lambda kind: owned(policy, snapshot, kind)),
            "carried": supply_rows(policy, snapshot, lambda kind: carried(snapshot, kind)),
            "equipment_owned": {"missing": owned_gear, "ready": not owned_gear,
                                "judged": "worn" if chosen is None else "owned-search"},
            "equipment_worn": {"missing": worn, "ready": not worn}}


def ready(rows: dict) -> bool:
    return bool(rows) and all(row["ready"] for row in rows.values())


def observe(policy, snapshot) -> None:
    """Measure the readiness on a town board and hand it to the preparation phase (finale_prep,
    the one owner of the switch); count the expedition's Restore Mana uses."""
    from hengbot import finale_prep  # import cycle
    held = memory(policy)
    if held.small_floor_pending is not None and snapshot.turn is not None:
        # The pref command spends no game time: the next board after it is its answer.
        held.small_floor_set = True
        held.small_floor_pending = None
    if snapshot.in_town:
        if held.in_town is False:
            held.owned_searched = False  # a new visit: the owned gear is searched again
        held.in_town = True
        held.restore_mana_used = 0
        held.restore_mana_seen = None
        if not preparing(snapshot):
            held.supplied = False
            held.report = {}
            finale_prep.observe(policy, snapshot, None)
            return
        held.report = rows = readiness(policy, snapshot)
        held.supplied = ready(rows["owned"])
        _keep_home_counts(policy)
        finale_prep.observe(policy, snapshot, rows)
        return
    held.in_town = False
    held.teleport_tour_done = False
    from hengbot import finale_bm_tour, finale_teleport_tour  # import cycle
    finale_teleport_tour.forget_trip(policy)
    finale_bm_tour.forget_trip(policy)
    finale_prep.observe(policy, snapshot, None)
    now = carried(snapshot, RESTORE_MANA)
    if (held.restore_mana_seen is not None and now < held.restore_mana_seen
            and on_finale_floor(snapshot)):
        held.restore_mana_used += held.restore_mana_seen - now
    held.restore_mana_seen = now


def census_known(policy) -> bool:
    """The Home's counts are known: a current census, or the one kept across the trip."""
    held = getattr(policy, MEMORY, None)
    return _census_current(policy) or getattr(held, "home_counts", None) is not None


def supplied(policy) -> bool:
    """The supplies are owned."""
    held = getattr(policy, MEMORY, None)
    return bool(held is not None and held.supplied)


def carrying(policy) -> bool:
    """The finale's carry, ranking and weight allowance hold (finale_prep ``carrying``)."""
    from hengbot import finale_prep  # import cycle
    return finale_prep.carrying(policy)


def feasibility_due(policy, snapshot) -> bool:
    """policy_equipment's read-only search over the owned gear in the finale's rank: the
    preparation phase's check step (finale_prep ``owned_search_due``)."""
    from hengbot import finale_prep  # import cycle
    return preparing(snapshot) and finale_prep.owned_search_due(policy)


def lifted(policy) -> bool:
    """The 95F cap is lifted (finale_prep ``lifted``: the phase's recall step and the expedition)."""
    from hengbot import finale_prep  # import cycle
    return finale_prep.lifted(policy)


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


def no_ammunition(policy, snapshot) -> bool:
    """Owner 2026-11-23 (verbatim) 「魔道具術師は決戦で矢は撃たない。全て自宅に預ける。」: a
    Magic-Eater in the finale -- the preparation phase from its ammunition step on and the
    expedition (finale_prep ``ammo_barred``: the lifted cap holds on the relay floors too), or
    on 99F/100F -- carries no ammunition and fires none.

    Readers: the carry target every purchase, Home withdrawal and retention reads
    (me_deep_launcher ``ammo_unneeded``), so the stacks are deposited at the Home and none is
    bought or taken out; the rounds the launcher fires (policy ``_matching_ammo``, out of town)
    and the launcher's expected shot (attack_expectation ``launcher_usable``), so no attack
    choice fires; the floor piles of ammunition alone (policy_helpers ``_floor_pile_is_junk``),
    so none is picked up; the unused-ammo junk class (policy_helpers ``_junk_class``), so a stack
    another launcher fires is deposited too, not destroyed.  The launcher itself stays worn for
    its abilities (owner 2026-11-18 「弓枠は追加能力や耐性のみで評価する」)."""
    player = getattr(snapshot, "player", None)
    if getattr(player, "class_id", None) != PLAYER_CLASS_MAGIC_EATER:
        return False
    from hengbot import finale_prep  # import cycle
    if finale_prep.ammo_barred(policy):
        return True
    return (not getattr(snapshot, "in_town", True) and hasattr(snapshot, "floor_key")
            and on_finale_floor(snapshot))


# -- the supplies ------------------------------------------------------------------

def carry_target(policy, snapshot, item) -> int | None:
    """The finale's carry of ``item``'s kind once the supplies and the equipment are owned
    (owner 2026-11-20 Q9 「準備がそろってから」), else None."""
    if not preparing(snapshot) or not carrying(policy) or not getattr(item, "aware", True):
        return None
    kind = _kind(item)
    if kind == RESTORE_MANA:
        return restore_mana_carry(policy, snapshot)
    from hengbot import finale_prep  # import cycle
    from hengbot.magic_eater_devices import SV_WAND_WONDER
    from hengbot.model import TVAL_WAND
    if kind == (TVAL_WAND, SV_WAND_WONDER) and finale_prep.food_wanted(snapshot):
        # Owner 2026-11-21 「謎の魔法棒を銘を分けて3本持って食料とする」 (finale_prep's food step).
        return finale_prep.FOOD_WANDS
    if kind == RESTORING:
        return RESTORING_CARRY
    return CARRY.get(kind)


def shortage(policy, snapshot, kind) -> int:
    """What the purchases still owe the count of ``kind``: the stock owned (pack and Home) while
    the character prepares."""
    if not preparing(snapshot):
        return 0
    target = restore_mana_carry(policy, snapshot) if kind == RESTORE_MANA else CARRY.get(kind)
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
    if _kind(item) != TELEPORT or not preparing(snapshot) or not carrying(policy):
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
    """A Black Market *Healing* toward the carry (the table buys none otherwise), or a Scroll of
    Reset Recall while Angband's recall depth is refused and none is carried (reset_recall, owner
    2026-11-21 「闇市に並んだフロア・リセットの巻物があれば使って95Fに戻す」)."""
    from hengbot import reset_recall  # import cycle
    if reset_recall.is_reset_recall(item):
        return reset_recall.wanted(policy, snapshot) and reset_recall.carried(snapshot) is None
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
    if limit is None or not preparing(snapshot) or not carrying(policy):
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
    held = memory(policy)
    return bool(lifted(policy) and not held.small_floor_set
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


def town_recall_key(policy, snapshot, key) -> str | None:
    """Owner 2026-11-20 Q8: in town, the option before the Word of Recall read toward Angband
    (``town:recall-to-angband`` with Angband's recall depth at the 95F exploration or deeper), else
    None."""
    if (not snapshot.in_town or not key or policy.last_reason != "town:recall-to-angband"
            or angband_depth(snapshot) < PREPARE_DEPTH):
        return None
    return small_floor_key(policy, snapshot)


def describe(policy) -> dict | None:
    held = getattr(policy, MEMORY, None)
    if held is None:
        return None
    from hengbot import finale_prep  # import cycle
    return {"supplied": held.supplied, "phase": finale_prep.describe(policy),
            "report": held.report, "small_floor_set": held.small_floor_set,
            "restore_mana_used": held.restore_mana_used}
