"""The Magic-Eater's absorption and class-16 uses (cmd-magiceat.cpp / mind-magic-eater.cpp).

``G`` + item absorbs a device; ``mBp`` + direction fires the Magic Missile wand;
``mA`` + I2A(sval) casts the staff sequence's powers.  The walk is me_menu's.
"""

from dataclasses import dataclass, replace
import re

from hengbot.input_executor import Continuation, ScreenKind
from hengbot.magic_eater import ABSORB_REASON, MISSILE_REASON
from hengbot.me_menu import (
    EMPTY, MagicEaterMenu, find_power_row, label_in_view, owned_item_prompt,
)


ABSORB_PROMPTS = ("どのアイテムの魔力を取り込みますか?", "Gain power of which item?")
IDENTIFY_PROMPTS = ("どのアイテムを鑑定しますか?", "Identify which item?")


@dataclass(frozen=True)
class MagicEaterStep(Continuation):
    stage: str = "kind"
    attempts: int = 0
    kind: str = "wand"   # "staff" for the absorbed staff powers
    sval: int = 15       # the power (I2A(sval) is its list letter)
    target: str = ""     # the Identify power's item address


# The class-16 staff sequence (me_staff_sequence): ``mA`` + I2A(sval), with
# the Identify power's inventory target.  Only that module composes ``mA``.
_STAFF_POWER_KEY = re.compile(r"mA(?P<letter>[fk])(?P<target>[a-w]?)")


def compile_magic_eater(key, owner):
    if owner == MISSILE_REASON and key == "R100\r":
        # Reuse the production rest prompt gate, allowing a refusal to return
        # directly to command input without leaving a required answer pending.
        from hengbot.observed_input import compile_observed_input
        prefix, steps = compile_observed_input(
            key, ScreenKind.COMMAND, None, "q34-recharge-prompt", [])
        return prefix, [replace(step, optional=True) for step in steps]
    if owner == ABSORB_REASON and re.fullmatch(r"G[a-z]", key):
        return "G", [MagicEaterStep(frozenset(), key[1], stage="absorb")]
    if owner == MISSILE_REASON and re.fullmatch(r"mBp[1-9]", key):
        return "m", [MagicEaterStep(frozenset(), key[-1])]
    staff = _STAFF_POWER_KEY.fullmatch(key)
    if staff is not None:
        sval = ord(staff["letter"]) - ord("a")
        if (sval == 5) != bool(staff["target"]):
            raise ValueError("invalid Magic-Eater staff operation")
        return "m", [MagicEaterStep(frozenset(), "", kind="staff", sval=sval,
                                    target=staff["target"])]
    if owner in {ABSORB_REASON, MISSILE_REASON}:
        raise ValueError("invalid Magic-Eater operation")
    return None


@dataclass(frozen=True)
class _ListedPower:
    names: tuple[str, str]
    kind: str


_POWERS = {("wand", 15): _ListedPower(("マジック・ミサイル", "Magic Missile"), "wand"),
           ("staff", 5): _ListedPower(("鑑定", "Perception"), "staff"),
           ("staff", 10): _ListedPower(("財宝感知", "Treasure Location"), "staff")}
_MISSILE = _POWERS[("wand", 15)]


def _inventory_slot(board, slot):
    return next((item for item in (board or {}).get("inventory", ())
                 if item.get("slot") == slot), None)


class AbsorbedUseMenu(MagicEaterMenu):
    step_type = MagicEaterStep
    compile = staticmethod(compile_magic_eater)
    terminal_name = "magic-eater"
    stall_text = "Magic-Eater menu made no progress"
    unexpected_text = "unexpected prompt after Magic-Eater answer"
    unasked_stages = frozenset({"aim"})
    spent_texts = EMPTY
    # A ValueError raised while the answer is posted (and from what the post
    # goes on to run) is handled as a refusal, unlike the other uses.
    guards_post = True

    def _absorb_stage(self, step, seen, operation):
        details = owned_item_prompt(seen, ABSORB_PROMPTS, "unowned absorption prompt")
        area, menu = details.get("area"), details.get("menu")
        if area == "floor" and "inventory" in details.get("areas", ()):
            return "6" if menu else "/", "absorb"
        if area != "inventory" or menu not in {True, False}:
            raise ValueError("unowned absorption item area")
        if menu:
            name = (_inventory_slot(operation.observation, step.keys) or {}).get("name")
            selected = [line.strip() for line in seen.lines[1:24]
                        if line.strip().startswith(("》", "> "))]
            if not name or len(selected) != 1:
                raise ValueError("unrecognized absorption menu cursor")
            return ("\r", "done") if name in selected[0] else ("2", "absorb")
        return label_in_view(details, step.keys, "absorption slot outside observed labels"), "done"

    def _identify_stage(self, step, seen, operation):
        # staff_effect's identify asks for the item (IDENTIFY_ITEM_PROMPT).
        details = owned_item_prompt(seen, IDENTIFY_PROMPTS, "unowned Magic-Eater identify prompt")
        if details.get("area") != "inventory" or details.get("menu"):
            raise ValueError("unowned Magic-Eater identify item area")
        return label_in_view(details, step.target, "identify target outside observed labels"), "done"

    stages = {"absorb": _absorb_stage,
              "kind": MagicEaterMenu.kind_stage,
              "power": MagicEaterMenu.power_stage,
              "target": _identify_stage,
              "aim": MagicEaterMenu.aim_stage}

    def before_post(self, executor, step, operation, deadline):
        if step.stage != "absorb":
            return
        state = executor._request("state", deadline, map=True)
        old = _inventory_slot(operation.observation, step.keys)
        current = _inventory_slot(state, step.keys)
        if old is None or current is None or any(
                old.get(field) != current.get(field)
                for field in ("tval", "sval", "name", "known", "charges", "count")):
            raise ValueError("absorption item changed")
        executor._bound_state_value = state

    def nothing_absorbed(self, step, operation):
        operation.magic_eater_wand_charges = -1

    def closes_refused_prompt(self, step, seen, operation):
        # Missing/unusable powers and bounded menu failures must return to
        # command input before the next policy decision can throw a torch.
        staff = step.kind == "staff"
        if not (operation.owner == MISSILE_REASON or staff):
            return False
        if not super().closes_refused_prompt(step, seen, operation):
            return False
        if not staff:
            operation.magic_eater_wand_charges = (
                -1 if find_power_row(seen.lines, _MISSILE) is None else 0)
        return True

    def power_of(self, step):
        return _POWERS[(step.kind, step.sval)]

    def after_power(self, step):
        if step.kind != "staff":
            return "aim"
        return "target" if step.target else "done"

    def list_kind(self, step):
        return "staff" if step.kind == "staff" else None

    def row_read(self, step, row, operation):
        if step.kind != "staff":
            operation.magic_eater_wand_charges = row.first

    def power_spent(self, step, operation):
        if step.kind != "staff":
            operation.magic_eater_wand_charges = 0


ABSORBED_USE = AbsorbedUseMenu()
