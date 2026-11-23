"""Compile historical composed keys into observed input waits.

Only already classified or recorded UI forms are changed here. Unrecorded
forms retain the baseline pending the R2 captures listed in the audit report.
The operation and its continuations are transient executor state, not policy
checkpoint attributes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from collections.abc import Mapping

from hengbot.angband_finale import SMALL_FLOOR_MACRO
from hengbot.arena import ENTER_KEY, ENTER_KEY_PATTERN, ENTER_REASON, POSTER_KEY, POSTER_KEY_PATTERN, POSTER_REASON
from hengbot.armor_smith import RAISE_KEY_PATTERN, RAISE_REASON
from hengbot.me_inn_refill import REST_KEY, REST_KEY_PATTERN, REST_REASONS
from hengbot.input_executor import (
    BUILDING_ENCHANT_PROMPTS, Continuation, RECALL_DUNGEON_PROMPTS, ScreenKind,
    WIELD_SLOT_PROMPTS,
)
from hengbot.morivant_tower import RECHARGE_ALL_REASONS
from hengbot.zul_trip import CURE_KEY, CURE_KEY_PATTERN, CURE_REASON
from hengbot.policy_identification import SOURCE_PROMPT, IDENTIFY_ITEM_PROMPT
from hengbot.policy_constants import (
    ALTER_KEY, CHARACTER_DUMP_MACRO, EASY_DIRECTION_COMMANDS, HOME_CHARACTER_DUMP_MACRO,
    ENTER_DUNGEON_MACRO, STORE_HOME,
    IN_STORE_BUY_REASON,
)


_QUAFF = ("どの薬を飲みますか?",)
_WIELD = ("どれを装備しますか?",)
_TAKEOFF = ("どれを装備からはずしますか?",)
_HAND = WIELD_SLOT_PROMPTS
_GET = ("どのアイテムを取りますか?",)
_PUT = ("どのアイテムを置きますか?",)
_BUY = ("どの品物が欲しいんだい?",)
_QUANTITY = (r"\s*いくつですか \(1-\d+\):(?: .*)?",)
_PRICE = (r"\s*買値 \$\d+ で買いますか？\[Y/n\]",)
# cmd-action/cmd-attack.cpp do_cmd_attack: input_check before hitting a visible
# non-hostile monster (input_check appends "[y/n]").
_ATTACK_FRIEND = (r"\s*(?:本当に攻撃しますか？|Really hit it\? )\s*\[[Yy]/[Nn]\]\s*",)


# Whole-bot maintainability review 2026-11-23 K4, (a)-3 (record only); the aimed item commands
# are observed since the owner answer (b)-5 (AIMED_ITEM_COMMANDS below).
# The questions a command asks after its key, in order, as the game source asks them.  A
# composed key (command + item letter + direction, ...) that this entry passes through whole
# relies on every non-optional question appearing; when one does not (a rod that does not aim,
# no launcher, a -more- in between) the rest of the key becomes the next command (a move).
# ``composed_passthrough`` names such a key so the executor's input-context log counts them.
@dataclass(frozen=True)
class ExpectedPrompt:
    kinds: frozenset        # the ScreenKinds that may ask here (one of them)
    optional: bool          # the game may skip this question (see ``when``)
    when: str = ""          # when it is asked or skipped (game source)


def _prompt(*kinds, optional=False, when=""):
    return ExpectedPrompt(frozenset(kinds), optional, when)


_ITEM = _prompt(ScreenKind.ITEM_SOURCE)
# target/target-getter.cpp get_aim_dir: asks unless command_dir is already set (a repeat) or
# use_old_target holds a valid target.  '*' (and ' ', Return) there opens target_set
# (target-setter.cpp switch_target_input / switch_next_grid_command): 't'/'.'/'5'/'0' sets the
# target and ends the mode, 'p' puts the cursor on the player, a direction moves it.
_AIM = _prompt(ScreenKind.DIRECTION, when="get_aim_dir")
COMMAND_PROMPTS: dict[str, tuple[ExpectedPrompt, ...]] = {
    # cmd-quaff.cpp:40 「どの薬を飲みますか?」
    "q": (_ITEM,),
    # cmd-eat.cpp:314 「どれを食べますか?」
    "E": (_ITEM,),
    # cmd-read.cpp:41 「どの巻物を読みますか?」; identify/enchant scrolls ask the target item,
    # Word of Recall off the dungeon floors asks choose_dungeon (spells-world.cpp).
    "r": (_ITEM, _prompt(ScreenKind.ITEM_TARGET, ScreenKind.DUNGEON_CHOICE, optional=True,
                         when="identify/enchant target; recall destination on the surface")),
    # cmd-usestaff.cpp:321 「どの杖を使いますか?」; the Perception staff asks the target item.
    "u": (_ITEM, _prompt(ScreenKind.ITEM_TARGET, optional=True, when="Perception staff")),
    # cmd-zapwand.cpp:336 「どの魔法棒で狙いますか?」; zapwand-execution.cpp:51 get_aim_dir
    # always, except a floor stack of more than one (message, no question).
    "a": (_ITEM, _AIM),
    # cmd-zaprod.cpp:301 「どのロッドを振りますか?」; zaprod-execution.cpp:54 get_aim_dir only
    # when is_aiming_rod() or the rod is not aware; Recall on the surface asks choose_dungeon.
    "z": (_ITEM, _prompt(ScreenKind.DIRECTION, ScreenKind.DUNGEON_CHOICE, optional=True,
                         when="aiming or unaware rod; recall destination on the surface")),
    # cmd-shoot.cpp:57 「どれを撃ちますか?」 (no launcher, the Crimson or a harp: a message and
    # no question at all); combat/shoot.cpp:536 exe_fire get_aim_dir.
    "f": (_ITEM, _AIM),
    # throw-execution.cpp:346 「どのアイテムを投げますか?」, :140 calc_throw_grid get_aim_dir.
    "v": (_ITEM, _AIM),
    # cmd-tunnel.cpp:45 get_rep_dir (always asks; no easy_* option).
    "T": (_prompt(ScreenKind.DIRECTION, when="get_rep_dir"),),
    # cmd-others.cpp:66 exe_alter get_rep_dir; cmd-attack.cpp input_check before a visible
    # non-hostile monster.
    "+": (_prompt(ScreenKind.DIRECTION, when="get_rep_dir"),
          _prompt(ScreenKind.CONFIRM, optional=True, when="visible non-hostile monster")),
    # cmd-open-close.cpp do_cmd_open/close/disarm: get_rep_dir is skipped by easy_open /
    # easy_disarm when exactly one candidate is around (see the gate below).
    "o": (_prompt(ScreenKind.DIRECTION, optional=True, when="easy_open: one closed door/chest"),),
    "c": (_prompt(ScreenKind.DIRECTION, optional=True, when="easy_open: one open door"),),
    "D": (_prompt(ScreenKind.DIRECTION, optional=True, when="easy_disarm: one trap/chest"),),
}

# The composers outside this entry that append a direction or a target walk to a command key.
# scripts/composed_key_lint.py fails on an unlisted one (or a count that differs).
# Suffix kinds: "direction" (get_aim_dir/get_rep_dir digit), "target-cursor" ('*' then
# target_set keys, ``*t5\x1b`` / ``*p<moves>t5\x1b``), "item-target" (an identify/enchant
# target letter), "floor-item" ('-'), "dungeon-choice" (the recall destination).
# reserved_item_command(..., suffix=...) calls: (module, function) -> (calls, suffix kinds).
COMPOSED_SUFFIX_SITES: dict[tuple[str, str], tuple[int, frozenset]] = {
    ("arena", "_shot_key"): (1, frozenset({"direction"})),
    ("breeder_area_attack", "_use"): (1, frozenset({"direction"})),
    ("floor_identify", "_source_key"): (1, frozenset({"floor-item"})),
    ("magic_eater", "planned_throw_key"): (1, frozenset({"direction"})),
    ("me_q1_torch", "attack_key"): (1, frozenset({"direction"})),
    ("me_ranged_first", "_use"): (1, frozenset({"direction"})),
    ("policy", "_floor_item_identify_key"): (1, frozenset({"floor-item"})),
    ("policy", "_read_key"): (1, frozenset({"item-target", "floor-item", "dungeon-choice"})),
    ("policy", "validate_read_key"): (1, frozenset({"item-target", "floor-item",
                                                     "dungeon-choice"})),
    ("policy", "_town_recall_device_key"): (1, frozenset({"dungeon-choice"})),
    ("policy_combat", "_adjacent_ranged_key"): (1, frozenset({"direction"})),
    ("policy_combat", "_ranged_attack_key"): (3, frozenset({"direction", "target-cursor"})),
    ("policy_home", "_home_disposal_processing_key"): (1, frozenset({"item-target"})),
    ("policy_identification", "_identify_carried_item_key"): (1, frozenset({"item-target"})),
    ("policy_quest", "_q2_ranged_core_key"): (2, frozenset({"direction", "target-cursor"})),
    ("policy_quest", "_q2_breach_key"): (1, frozenset({"direction"})),
    ("policy_quest", "_quest_execute_key"): (2, frozenset({"direction"})),
    ("policy_town", "_town_device_processing_key"): (1, frozenset({"item-target"})),
    ("policy_town", "_town_item_processing_dispatch_key"): (1, frozenset({"item-target"})),
    ("quest25_battle", "_disarm_device_key"): (1, frozenset({"direction"})),
    ("quest25_battle", "_carried_grid_key"): (1, frozenset({"target-cursor"})),
    ("quest25_battle", "_launcher_grid_key"): (1, frozenset({"target-cursor"})),
    ("quest_lure_approach", "_fire_key"): (1, frozenset({"target-cursor"})),
    ("quest_plan_base", "hall_away_key"): (1, frozenset({"direction"})),
    ("retreat_enclosure", "_door_beam_key"): (1, frozenset({"direction"})),
    ("sealed_loot", "_trap_key"): (1, frozenset({"direction"})),
    ("sealed_pocket", "wand_key"): (1, frozenset({"direction"})),
    ("supply_fight", "_spend"): (1, frozenset({"direction"})),
    ("teleport_follower", "away_key"): (1, frozenset({"direction"})),
}
# ``KEY + direction`` / ``'*p' + cursor walk`` written outside reserved_item_command:
# (module, function) -> (sites, how this entry sends it).  "observed": the direction is
# released only at its observed question; "passthrough": sent composed.
COMPOSED_APPEND_SITES: dict[tuple[str, str], tuple[int, str]] = {
    ("blind_strike", "strike_key"): (1, "observed"),           # '+' (ALTER_KEY gate)
    ("magic_eater", "q34_missile_key"): (1, "observed"),       # 'mBp' (magic_eater_input)
    ("me_q1_torch", "attack_key"): (1, "observed"),            # 'mBp'
    ("me_ranged_first", "_fire_missile"): (1, "observed"),     # 'mBp'
    ("policy_fundraising", "_mining_tunnel_key"): (1, "passthrough"),  # 'T'
    ("policy_identification", "_chest_processing_key"): (2, "observed"),  # 'D' / 'o'
    ("policy_quest", "_q2_ranged_core_key"): (1, "observed"),   # '*p' walk (fire suffix, (b)-5)
    ("policy_quest", "_q2_breach_key"): (1, "passthrough"),     # 'T'
    ("policy_quest", "_quest_sequence_door_key"): (1, "observed"),  # 'o'
    ("policy_quest", "_quest_execute_key"): (1, "observed"),    # 'o'
    ("policy_town", "_town_kill_mob_key"): (1, "passthrough"),  # '+' dir 'y'
    ("quest25_battle", "_cursor_suffix"): (1, "observed"),      # '*p' walk (fire/device, (b)-5)
    ("quest25_battle", "_ambush"): (1, "observed"),             # 'c'
    ("quest_find_exit", "_dig"): (1, "passthrough"),            # 'T'
    ("quest_lure_approach", "_fire_key"): (1, "observed"),      # '*p' walk (device, (b)-5)
    ("unseen_strike", "key"): (1, "observed"),                  # '+'
}

# Owner answer (b)-5, 2026-11-23 「問いが出た時だけ方向を送る」: the aimed item commands (wand
# 'a', rod 'z', fire 'f', throw 'v') send the command and the item letter, and their direction or
# target walk only at the observed direction question (the easy_open fix 6bef1941c0 did the same
# for 'o'/'c'/'D').  get_aim_dir (target/target-getter.cpp) asks nothing with use_old_target and
# a valid target, a non-aiming known rod (zaprod-execution.cpp) asks nothing, and no launcher /
# no item prints a message instead; the trailing keys then fell to the command loop (a step, or
# '5' -> ',' stay still, lib/pref/pref-key.prf).  Suffix kinds "direction" and "target-cursor" of
# COMPOSED_SUFFIX_SITES go this way (scripts/composed_key_lint.py checks it).
AIMED_ITEM_COMMANDS = "azfv"
# target/target-setter.cpp: at get_aim_dir's question '*' opens target_set (TARGET_KILL); 'p'
# puts the cursor on the player (free mode) and a direction moves it; 't' sets the target and
# ends the mode (switch_target_input / switch_next_grid_command), so get_aim_dir returns at once.
# The composers' trailing ``5\x1b`` is read only while target_set still waits ('t' refused:
# can_target_monster_at_cursor false): '5' tries again, ESC leaves.  After a set target they were
# read as commands ('5' = ',' stay still, a game turn).  So each is released only on the
# observed target screen (ScreenKind.LOOK, the key guide on row 0).
_TARGET_WALK = re.compile(r"\*(?:p[1-9]*)?t")
_TARGET_RETRY = "5\x1b"


def aim_steps(suffix: str) -> list[Continuation] | None:
    """The observed answers of an aimed item command's ``suffix`` (a direction digit or a
    ``*t5\\x1b`` / ``*p<moves>t5\\x1b`` target walk), or None for another suffix."""
    if re.fullmatch(r"[1-9]", suffix):
        return [_answer(ScreenKind.DIRECTION, suffix, optional=True)]
    if suffix.endswith(_TARGET_RETRY) and _TARGET_WALK.fullmatch(suffix[:-len(_TARGET_RETRY)]):
        return [_answer(ScreenKind.DIRECTION, suffix[:-len(_TARGET_RETRY)], optional=True),
                *(_answer(ScreenKind.LOOK, retry, optional=True) for retry in _TARGET_RETRY)]
    return None


def _suffix_kind(command: str, tail: str) -> str:
    if not tail:
        return "none"
    if tail.startswith("*"):
        return "target-cursor"
    if re.fullmatch(r"[1-9]", tail[:1]):
        return "direction"
    if tail.startswith("-"):
        return "floor-item"
    return "item-target" if command in "ru" else "other"


def composed_passthrough(key: str, prefix: str) -> dict | None:
    """The record of a composed ``key`` sent whole (``prefix`` is what
    ``compile_observed_input`` made the first segment), or None.

    Record only: whether the questions of ``COMMAND_PROMPTS`` appeared is not observed
    for such a key, so each one is counted (review 2026-11-23 K4, (a)-3).
    """
    if not isinstance(key, str) or len(key) < 2 or prefix != key:
        return None
    plan = COMMAND_PROMPTS.get(key[0])
    if plan is None:
        return None
    item_first = ScreenKind.ITEM_SOURCE in plan[0].kinds
    tail = key[2:] if item_first else key[1:]
    return {
        "command": key[0],
        "key": key,
        "suffix": _suffix_kind(key[0], tail),
        "expected": [sorted(kind.value for kind in step.kinds) + (["optional"] if step.optional else [])
                     for step in plan],
    }


def _answer(kind, keys, feature=None, **options):
    return Continuation(frozenset({kind}), keys, feature, **options)


def _building_raise(label):
    """One raise at the armour smith, answered only on its observed prompts.

    market/building-enchanter.cpp: the chooser opens on the pack only when the
    pack holds armour.  'a' refused (no gold) leaves the menu up and both page
    answers fall away; a raise past the cap prints its failure over the menu.
    """
    prompts = "|".join(re.escape(prompt) for prompt in BUILDING_ENCHANT_PROMPTS)

    def page(keys, names):
        return _answer(ScreenKind.ITEM_SOURCE, keys, (rf"\((?:{names}):.*(?:{prompts})",),
                       exact_feature=True, feature_pattern=True, optional=True)
    return [_answer(ScreenKind.BUILDING, "a"), page("/", "持ち物|Inven"), page(label, "装備品|Equip")]


def _surface_recall_read(command, slot, board):
    """Whether ``r<slot>`` reads Word of Recall (or ``z<slot>`` zaps the Rod of
    Recall) where it asks a destination.

    spell-kind/spells-world.cpp recall_player: off the dungeon floors (town
    and wilderness) and with no recall active, choose_dungeon asks which
    dungeon to recall to.  Underground, or cancelling an active recall, it
    does not ask.  The rod calls the same recall_player (cmd-zaprod.cpp
    SV_ROD_RECALL).
    """
    from hengbot.model import SV_ROD_RECALL, SV_SCROLL_WORD_OF_RECALL, TVAL_ROD, TVAL_SCROLL

    device = {"r": (TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL),
              "z": (TVAL_ROD, SV_ROD_RECALL)}.get(command)
    if device is None or not isinstance(board, Mapping):
        return False
    floor = board.get("floor")
    player = board.get("player")
    if not isinstance(floor, Mapping) or floor.get("level") != 0:
        return False
    if isinstance(player, Mapping) and player.get("recalling"):
        return False
    return any(
        isinstance(item, Mapping) and item.get("slot") == slot
        and (item.get("tval"), item.get("sval")) == device
        for item in board.get("inventory", ()) or ())


def _split_page_switches(continuations):
    result = []
    for step in continuations:
        # '/' refreshes the chooser. Its selected item belongs to that new
        # observed page, rather than the inventory prompt preceding '/'.
        if len(step.keys) > 1 and step.keys.startswith("/") and step.kinds <= {
                ScreenKind.ITEM_SOURCE, ScreenKind.ITEM_TARGET}:
            if step.feature is None or step.feature_pattern:
                raise ValueError("page switch requires a bound item prompt")
            prompts = step.feature if isinstance(step.feature, tuple) else (step.feature,)
            equipment = tuple(
                r"\s*\((?:Equip|装備品):.*" + re.escape(prompt.rstrip())
                for prompt in prompts)
            result.extend((replace(step, keys="/"), replace(
                step, keys=step.keys[1:], feature=equipment,
                exact_feature=True, feature_pattern=True)))
        else:
            result.append(step)
    return result


def compile_observed_input(key: str, kind: ScreenKind | None,
                           board: Mapping | None, owner: str,
                           continuations: list[Continuation], *, screen: Mapping | None = None):
    """Return the initial key and separately observed continuation segments.

    The suffix literals cite live-screens cap-05/11/13/15/16/31 and live30.
    Read/device/identify, LOOK, knowledge and quantity reuse the established
    classifier and captured screens. Missing forms remain unfixed blockers.
    """
    if owner == IN_STORE_BUY_REASON and (key != "p" or not continuations):
        # SOL-DESIGN-store-reentry-20261003 3.1: an in-store purchase is only
        # 'p' followed by answers gated on its own observed prompts
        # (cli._in_store_buy_continuations); never a composed macro.
        raise ValueError("in-store buy without observed prompt gates")
    # The captured Class A store prompts are Japanese. The established
    # English store plans bind composed transactions to the observed store
    # boundary, with any existing quantity/confirmation gates kept separately.
    # Preserve those plans for every producer instead of imposing Japanese
    # chooser text on Home, calibration, equipment transactions or other shops.
    if kind is ScreenKind.STORE and key[:1] in {"p", "d", "g", " "} and any(
            "You may: p) Purchase an item." in str(line)
            for line in (screen or {}).get("lines", ())):
        return key, continuations
    continuations = _split_page_switches(continuations)
    from hengbot.me_menu_uses import compile_menu_key
    menu_plan = compile_menu_key(key, owner)
    if menu_plan is not None:
        prefix, steps = menu_plan
        return prefix, [*steps, *continuations]
    if owner == "shop:one-shot-buy":
        continuations = [
            replace(step, feature=_QUANTITY if ScreenKind.QUANTITY in step.kinds else _PRICE,
                    exact_feature=True, feature_pattern=True)
            if step.feature is None and step.kinds in (
                frozenset({ScreenKind.QUANTITY}), frozenset({ScreenKind.CONFIRM}))
            else step for step in continuations
        ]
    if not key or len(key) == 1:
        return key, continuations
    if (kind is ScreenKind.STORE and owner == "shop:one-shot-buy"
            and continuations
            and continuations[0].kinds == frozenset({ScreenKind.ITEM_SOURCE})
            and key.startswith("p") and key[1:] == continuations[0].keys):
        # The sender already bound this slot to the recorded store chooser.
        # Split its historical p+slot prefix without inserting a narrower
        # _BUY gate in front of that authoritative continuation.
        return "p", [replace(continuations[0], optional=False), *continuations[1:]]
    if owner == "bounty:cashout" and re.fullmatch(r"[1-9]cy+\x1b", key):
        # market/bounty.cpp: input_check flushes before each hand-over. Keep
        # the admitted terminal through its observed building and questions.
        confirmations = [
            _answer(ScreenKind.CONFIRM, "y", (
                r"(?:Hand .+ over\? |Convert .+ into money\? |.+を渡しますか？|.+ を換金しますか？)\s*\[[Yy]/n\]",
            ), exact_feature=True, feature_pattern=True, optional=True)
            for _ in key[2:-1]
        ]
        return key[0], [
            _answer(ScreenKind.BUILDING, "c"),
            *confirmations, _answer(ScreenKind.BUILDING, "\x1b"),
            *continuations,
        ]
    if owner in RECHARGE_ALL_REASONS and re.fullmatch(r"[1-9]ay\x1b", key):
        # market/building-recharger.cpp building_recharge_all: one
        # input_check after 'a'; no question when nothing needs a recharge
        # or the gold is short (msg_print only).  'y' answers only that
        # observed question, then ESC leaves the Tower.
        return key[0], [
            _answer(ScreenKind.BUILDING, "a"),
            _answer(ScreenKind.CONFIRM, "y", (
                r"(?:Recharge all items for \d+ gold\? |すべてのアイテムを ＄\d+ で再充填しますか？)\s*\[[Yy]/n\]",
            ), exact_feature=True, feature_pattern=True, optional=True),
            _answer(ScreenKind.BUILDING, "\x1b"),
            *continuations,
        ]
    if owner == POSTER_REASON and re.fullmatch(POSTER_KEY_PATTERN, key):
        # market/arena.cpp BACT_POSTER: a message over the kept menu, no time.  A defeated
        # character gets no menu (cmd-building.cpp 「敗者に用はない。」): both fall away.
        return key[0], [_answer(ScreenKind.BUILDING, POSTER_KEY, optional=True),
                        _answer(ScreenKind.BUILDING, "\x1b", optional=True), *continuations]
    if owner == ENTER_REASON and re.fullmatch(ENTER_KEY_PATTERN, key):
        # market/arena.cpp go_to_arena: the floor changes with no question below the
        # ceremony (the owner stops before it).  A refused entry leaves the menu up, and
        # the executor closes a menu with no answer left.
        return key[0], [_answer(ScreenKind.BUILDING, ENTER_KEY, optional=True), *continuations]
    if owner == CURE_REASON and re.fullmatch(CURE_KEY_PATTERN, key):
        # cmd-building.cpp BACT_LOSE_MUTATION: no question; each 'm' cures one
        # mutation and prints its message over the kept menu (a short purse or
        # no mutation left prints its refusal instead).  Every answer is
        # released only on the observed building menu.
        cures = [_answer(ScreenKind.BUILDING, CURE_KEY, optional=True) for _ in key[1:-1]]
        return key[0], [*cures, _answer(ScreenKind.BUILDING, "", optional=True), *continuations]
    if owner in REST_REASONS and re.fullmatch(REST_KEY_PATTERN, key):
        # cmd-building/cmd-inn.cpp stay_inn: no question; the stay prints its message over
        # the kept menu (a short purse, or a poisoned or cut character, prints its refusal
        # instead).  Both answers are released only on the observed building menu.
        return key[0], [_answer(ScreenKind.BUILDING, REST_KEY, optional=True),
                        _answer(ScreenKind.BUILDING, "", optional=True), *continuations]
    if owner == RAISE_REASON and re.fullmatch(RAISE_KEY_PATTERN, key):
        raises = [step for label in key[3::3] for step in _building_raise(label)]
        return key[0], [*raises, _answer(ScreenKind.BUILDING, "\x1b"), *continuations]
    command, tail = key[0], key[1:]
    # The once-mode sender also enters this common port. Reuse the same
    # established plans as the ordinary decision router instead of bypassing
    # their gates when the original composed macro arrives directly here.
    if key in {CHARACTER_DUMP_MACRO, HOME_CHARACTER_DUMP_MACRO, ENTER_DUNGEON_MACRO,
               SMALL_FLOOR_MACRO} \
            or re.fullmatch(r"ga{2,}", key):
        from hengbot.cli import (
            _home_modal_continuation, _dungeon_entrance_continuation,
            _floor_pile_pickup_continuations,
        )
        from hengbot.model import parse_snapshot
        snapshot = parse_snapshot(dict(board or {}), {})
        plan = (_home_modal_continuation(snapshot, key, owner)
                or _dungeon_entrance_continuation(snapshot, key, owner)
                or _floor_pile_pickup_continuations(snapshot, key))
        if plan is not None:
            first, steps = plan
            return first, [*steps, *continuations]
    store = (board or {}).get("store")
    home = isinstance(store, Mapping) and store.get("store_type") == STORE_HOME
    home = home or owner.startswith(("home:", "equipment-transaction:"))
    if kind is ScreenKind.COMMAND and command in "pdg" and owner.startswith(
            ("home:", "shop:", "equipment-transaction:withdraw",
             "equipment-transaction:deposit")):
        raise ValueError("store command on map screen")

    if command in EASY_DIRECTION_COMMANDS and re.fullmatch(r"[1-9]", tail) and (
            owner in {"chest:disarm", "chest:open"} or kind in (None, ScreenKind.COMMAND)):
        # The open / close / disarm of a door, a trap or a chest, from any producer.  With
        # easy_open / easy_disarm (option-types-table.cpp, both on), cmd-open-close.cpp
        # do_cmd_open sets command_dir itself when exactly one closed door (count_doors_traps
        # GridCountKind::CLOSED_DOOR, marked grids) or one non-empty chest (open-util.cpp
        # count_chests) and not both is around; do_cmd_close when exactly one open door is
        # (GridCountKind::OPEN); do_cmd_disarm when exactly one trap (the player's own grid
        # too) or one known trapped chest is.  get_rep_dir then asks no direction, and a
        # composed ``o6`` left the ``6`` to the next command: a step onto the opened door, or
        # an attack on a monster there.  n1-c life-221 (Quest 25, 2026-11-23): ``o3`` at [9,23]
        # walked onto [10,24], ``o6`` at [13,27] onto [13,28] beside the stairway monster,
        # ``o4`` at [11,20] into the druj's doorway [11,19].  So the command key goes alone and
        # the direction is released only at the observed direction question; otherwise it
        # falls away (bare command).  do_cmd_tunnel, do_cmd_bash, do_cmd_spike and exe_alter
        # always ask (get_rep_dir with no command_dir set).
        # cmd-open-close.cpp: a monster on that square is attacked instead, and
        # cmd-attack.cpp do_cmd_attack asks input_check 「本当に攻撃しますか？」 of a
        # visible non-hostile one.  A door or a chest is not worth turning a friend: 'n'
        # answers only that observed question (n1-c life-216, 2026-11-17 00:41).
        return command, [_answer(ScreenKind.DIRECTION, tail, optional=True),
                         _answer(ScreenKind.CONFIRM, "n", _ATTACK_FRIEND, exact_feature=True,
                                 feature_pattern=True, optional=True),
                         *continuations]
    if command == ALTER_KEY and re.fullmatch(r"[1-9]", tail):
        # cmd-others.cpp exe_alter: get_rep_dir asks the direction, then a
        # monster there is attacked, seen or not (no-wait:attack, blind strike).
        return command, [_answer(ScreenKind.DIRECTION, tail, optional=True), *continuations]

    if command == "~" and tail in {"9", "f"} and continuations:
        return command, [_answer(ScreenKind.KNOWLEDGE, tail), *continuations]
    if key in {"~9\x1b", "~9\x1b\x1b", "~f\x1b"}:
        feature = "home-inventory" if tail[0] == "9" else "skill-proficiency"
        return "~", [
            _answer(ScreenKind.KNOWLEDGE, tail[0]),
            _answer(ScreenKind.FILE_VIEWER, "\x1b", feature, exact_feature=True),
            _answer(ScreenKind.KNOWLEDGE, "\x1b"),
        ]
    if command == "l" and tail == "\x1b":
        return command, [_answer(ScreenKind.LOOK, tail), *continuations]
    if command == "R" and re.fullmatch(r"(?:\d+|[&*])\r", tail):
        return command, [_answer(ScreenKind.QUANTITY, tail,
            (r"(?:Rest|休憩) \(0-9999, .+\):(?: .*)?",),
            exact_feature=True, feature_pattern=True), *continuations]

    if command in AIMED_ITEM_COMMANDS and not (command == "z" and kind is ScreenKind.COMMAND) \
            and kind in (None, ScreenKind.COMMAND) and re.fullmatch(r"[a-z-]", tail[:1]):
        # Owner answer (b)-5 (AIMED_ITEM_COMMANDS): the command and the item letter go together
        # (the wand, launcher and throw choosers are not classified screens); the direction or
        # the target walk only at the observed question.  A rod on the command screen has its
        # observed chooser (below).
        aim = aim_steps(tail[1:])
        if aim is not None:
            return key[:2], [*aim, *continuations]

    if command in "qruz" and kind is ScreenKind.COMMAND:
        if not re.fullmatch(r"[a-z]", tail[:1]):
            raise ValueError("invalid item source address")
        source = SOURCE_PROMPT[command] if command in SOURCE_PROMPT else _QUAFF
        steps = [_answer(ScreenKind.ITEM_SOURCE, tail[0], source)]
        suffix = tail[1:]
        if _surface_recall_read(command, tail[0], board):
            # D22: the destination letter is released only at the observed
            # choose_dungeon prompt listing it.  Without one the executor
            # cancels the chooser under a named stop.
            if suffix:
                if not re.fullmatch(r"[a-z]", suffix):
                    raise ValueError("invalid recall destination address")
                steps.append(_answer(ScreenKind.DUNGEON_CHOICE, suffix,
                                     RECALL_DUNGEON_PROMPTS))
            return command, [*steps, *continuations]
        if suffix:
            aim = aim_steps(suffix) if command == "z" else None
            if aim is not None:
                # Owner answer (b)-5: an aiming (or unaware) rod asks the direction
                # (zaprod-execution.cpp get_aim_dir), a known non-aiming one does not.
                return command, [*steps, *aim, *continuations]
            if not (owner.startswith("identify:") or owner == "loot:identify-floor-item"):
                return key, continuations
            if owner.startswith("identify:full"):
                suffix = suffix.rstrip("\x1b")
            if suffix.startswith("/"):
                if owner != "identify:normal-equipped":
                    steps.append(_answer(ScreenKind.ITEM_TARGET, "/", IDENTIFY_ITEM_PROMPT))
                suffix = suffix[1:]
            if not re.fullmatch(r"[a-z-]", suffix):
                raise ValueError("invalid identify target address")
            steps.append(_answer(ScreenKind.ITEM_TARGET, suffix, IDENTIFY_ITEM_PROMPT))
        return command, [*steps, *continuations]

    if command in "wt":
        if not re.fullmatch(r"[a-zA-Z]", tail[:1]):
            raise ValueError("invalid equipment source address")
        steps = [_answer(ScreenKind.ITEM_SOURCE, tail[0],
                         _WIELD if command == "w" else _TAKEOFF)]
        suffix = tail[1:]
        if suffix:
            if command != "w" or suffix not in "()de":
                return key, continuations
            steps.append(_answer(ScreenKind.ITEM_TARGET, suffix, _HAND))
        return command, [*steps, *continuations]

    if kind is ScreenKind.STORE and command in "pdg ":
        try:
            return _store_plan(key, home, continuations)
        except ValueError:
            return key, continuations
    if command == "5" and tail and tail[0] in "pdg " and owner.startswith(
            ("home:", "equipment-transaction:", "shop:")):
        try:
            first, steps = _store_plan(tail, home, continuations)
        except ValueError:
            return key, continuations
        return command, [_answer(ScreenKind.STORE, first), *steps]
    return key, continuations


def _store_plan(key, home, following):
    command, tail = key[0], key[1:]
    steps = []
    if command == " ":
        if tail:
            next_command, next_steps = _store_plan(tail, home, following)
            steps.extend((_answer(ScreenKind.STORE, next_command), *next_steps))
        return command, steps
    if command not in "pdg" or not tail or not re.fullmatch(r"[a-zA-Z]", tail[0]):
        raise ValueError("needs live screen capture: store command/selector")
    feature = _PUT if command == "d" else _GET if home else _BUY
    if command == "d" and not home:
        raise ValueError("needs live screen capture: shop sale item chooser")
    steps.append(_answer(ScreenKind.ITEM_SOURCE, tail[0], feature))
    tail = tail[1:]
    quantity_match = re.match(r"\d+\r", tail)
    quantity = quantity_match[0] if quantity_match else "\r" if tail.startswith("\r\r") else ""
    if quantity:
        steps.append(_answer(ScreenKind.QUANTITY, quantity, _QUANTITY,
                             exact_feature=True, feature_pattern=True))
        tail = tail[len(quantity):]
    if tail.startswith("\r"):
        if home:
            raise ValueError("unexpected Home price confirmation")
        steps.append(_answer(ScreenKind.CONFIRM, "\r",
                             _PRICE,
                             exact_feature=True, feature_pattern=True))
        tail = tail[1:]
    if tail == "\x1b":
        steps.append(_answer(ScreenKind.STORE, tail))
    elif tail:
        next_command, next_steps = _store_plan(tail, home, [])
        steps.extend((_answer(ScreenKind.STORE, next_command), *next_steps))
    return command, [*steps, *following]
