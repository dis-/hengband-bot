"""Compile historical composed keys into observed input waits.

Only already classified or recorded UI forms are changed here. Unrecorded
forms retain the baseline pending the R2 captures listed in the audit report.
The operation and its continuations are transient executor state, not policy
checkpoint attributes.
"""

from __future__ import annotations

import re
from dataclasses import replace
from collections.abc import Mapping

from hengbot.input_executor import Continuation, ScreenKind
from hengbot.policy_identification import SOURCE_PROMPT, IDENTIFY_ITEM_PROMPT
from hengbot.policy_constants import (
    CHARACTER_DUMP_MACRO, HOME_CHARACTER_DUMP_MACRO, ENTER_DUNGEON_MACRO, STORE_HOME,
)


_QUAFF = ("どの薬を飲みますか?",)
_WIELD = ("どれを装備しますか?",)
_TAKEOFF = ("どれを装備からはずしますか?",)
_HAND = ("どちらの手に装備しますか?",)
_GET = ("どのアイテムを取りますか?",)
_PUT = ("どのアイテムを置きますか?",)
_BUY = ("どの品物が欲しいんだい?",)
_QUANTITY = (r"\s*いくつですか \(1-\d+\):(?: .*)?",)
_PRICE = (r"\s*買値 \$\d+ で買いますか？\[Y/n\]",)


def _answer(kind, keys, feature=None, **options):
    return Continuation(frozenset({kind}), keys, feature, **options)


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
            and key == "p" + continuations[0].keys):
        # The sender already bound this slot to the recorded store chooser.
        # Split its historical p+slot prefix without inserting a narrower
        # _BUY gate in front of that authoritative continuation.
        return "p", [replace(continuations[0], optional=False), *continuations[1:]]
    command, tail = key[0], key[1:]
    # The once-mode sender also enters this common port. Reuse the same
    # established plans as the ordinary decision router instead of bypassing
    # their gates when the original composed macro arrives directly here.
    if key in {CHARACTER_DUMP_MACRO, HOME_CHARACTER_DUMP_MACRO, ENTER_DUNGEON_MACRO} \
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
    home = home or owner.startswith(("home:", "calibration:", "equipment-transaction:"))
    if kind is ScreenKind.COMMAND and command in "pdg" and owner.startswith(
            ("home:", "shop:", "calibration:", "equipment-transaction:withdraw",
             "equipment-transaction:deposit")):
        raise ValueError("store command on map screen")

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

    if command in "qruz" and kind is ScreenKind.COMMAND:
        if not re.fullmatch(r"[a-z]", tail[:1]):
            raise ValueError("invalid item source address")
        source = SOURCE_PROMPT[command] if command in SOURCE_PROMPT else _QUAFF
        steps = [_answer(ScreenKind.ITEM_SOURCE, tail[0], source)]
        suffix = tail[1:]
        if suffix:
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
            ("home:", "calibration:", "equipment-transaction:", "shop:")):
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
