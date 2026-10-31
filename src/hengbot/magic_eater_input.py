"""Observed Magic-Eater input protocol (cmd-magiceat.cpp / mind-magic-eater.cpp).

Each answer is one executor segment. Power letters and charges come from the
current list; menu movement is followed by another observation before Enter.
"""

from dataclasses import dataclass, replace
import re

from hengbot.input_executor import Continuation, ScreenKind
from hengbot.input_context import read_input_view
from hengbot.magic_eater import ABSORB_REASON, MISSILE_REASON


ABSORB_PROMPTS = ("どのアイテムの魔力を取り込みますか?", "Gain power of which item?")
TYPE_PROMPTS = ("[A] 杖, [B] 魔法棒, [C] ロッド:", "[A] staff, [B] wand, [C] rod:")
MENU_PROMPTS = ("どの種類の魔法を使いますか？", "Which type of magic do you use?")
POWER_PROMPTS = ("('*'で一覧, ESCで中断) どの魔力を使いますか？",
                 "(*=List, ESC=exit) Use which power?")
FAILURES = ("呪文をうまく唱えられなかった！", "You failed to get the magic off!",
            "その種類の魔法は覚えていない！", "You don't have that type of magic!")
EMPTY = ("その魔法は使用回数が切れている。", "The magic has no charges left.")
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


def kind_menu_wait(reading, row0, prompts):
    """Whether the game waits in the use_menu kind menu titled by ``prompts``.

    select_magic_eater's cursor loop read raw inkey() and published null
    until game 8efed08ef7, which publishes it as command_char with the menu
    line as the prompt.  Either way the complete source-derived menu is
    still required (``_wand_menu_answer``).
    """
    if reading.source == "null":
        return row0 in prompts
    return reading.kind == "command_char" and reading.prompt.strip() in prompts


def _wand_menu_answer(lines, wanted=1):
    choices = [line.strip() for line in lines[2:5]]
    if len(choices) != 3 or not all(
            choice.endswith(names) for choice, names in zip(
                choices, (("杖", "staff"), ("魔法棒", "wand"), ("ロッド", "rod")))):
        raise ValueError("unrecognized Magic-Eater type menu")
    selected = [index for index, choice in enumerate(choices)
                if choice.startswith(("》", ">"))]
    if len(selected) != 1:
        raise ValueError("missing Magic-Eater menu cursor")
    if selected[0] == wanted:
        return "\r"
    return "2" if selected[0] < wanted else "8"


_POWER_NAMES = {("wand", 15): ("マジック・ミサイル", "Magic Missile"),
                ("staff", 5): ("鑑定", "Perception"),
                ("staff", 10): ("財宝感知", "Treasure Location")}


def _power_row(lines, kind="wand", sval=15):
    # Two 40-cell columns. The source prints an ASCII letter or a menu
    # cursor before the baseitem name, then current/max and failure percent.
    names = "|".join(re.escape(name) for name in _POWER_NAMES[(kind, sval)])
    pattern = r"(?P<label>[a-z0-9]\)|》|> |  )\s*(?:" + names + r")\s+(\d+)\s*/\s*(\d+)\s+\d+%"
    for line in lines[2:20]:
        match = re.search(pattern, line)
        if match:
            return match.group("label"), int(match.group(2))
    return None


# One list entry as cmd-magiceat.cpp prints it: a letter or menu cursor, the
# baseitem name, then "cur/max" (staff/wand), "充填:c/n" or "(c/n)" (rod: c of
# n absorbed rods are charging) and the failure percent. Rows sit in two
# 40-cell columns, so one screen line may hold two entries.
_LIST_ENTRY = re.compile(
    r"(?:(?:[a-z0-9]\)|》|>)\s?)?(?P<name>\S.*?)\s+(?P<rod>充填:\s*|\(\s*)?"
    r"(?P<first>\d+)\s*/\s*(?P<second>\d+)\)?\s*(?P<fail>\d+)%")
_ROD_HEADERS = ("状態", "Stat")


def observed_power_list(lines, kind=None):
    """The power list exactly as displayed, or None when it is not on screen.

    Viewer-only (spectate.json): no decision reads this projection.  The
    executor only ever answers the wand type (``B`` or the menu's 魔法棒), so
    a list without the rod header is the wand list.
    """
    rows = []
    for line in lines[2:20]:
        for match in _LIST_ENTRY.finditer(line):
            name = match.group("name").strip()
            if name.startswith(("》", ">")):
                name = name.lstrip("》> ").strip()
            first, second = int(match.group("first")), int(match.group("second"))
            fail = int(match.group("fail"))
            row = {"name": name, "fail": fail, "success": 100 - fail}
            if match.group("rod") is not None:
                row.update(charging=first, max=second)
            else:
                row.update(current=first, max=second)
            rows.append(row)
    if not rows:
        return None
    header = lines[1] if len(lines) > 1 else ""
    rod = any(text in header for text in _ROD_HEADERS) or "charging" in rows[0]
    return {"kind": kind or ("rod" if rod else "wand"), "rows": rows}


def _owns_power_prompt(reading):
    return (reading.kind in {"spell", "command_char"}
            and reading.prompt.rstrip() in POWER_PROMPTS)


def _answer(step, screen, operation):
    reading, lines = read_input_view(screen)
    prompt = reading.prompt.rstrip()
    row0 = lines[0].strip() if lines else ""
    if step.stage == "absorb":
        if reading.kind != "item" or not prompt.endswith(ABSORB_PROMPTS):
            raise ValueError("unowned absorption prompt")
        area = reading.details.get("area")
        menu = reading.details.get("menu")
        if area == "floor" and "inventory" in reading.details.get("areas", ()):
            return "6" if menu else "/", "absorb"
        if area != "inventory" or menu not in {True, False}:
            raise ValueError("unowned absorption item area")
        if menu:
            old = next((item for item in (operation.observation or {}).get("inventory", ())
                        if item.get("slot") == step.keys), {})
            name = old.get("name")
            selected = [line.strip() for line in lines[1:24]
                        if line.strip().startswith(("》", "> "))]
            if not name or len(selected) != 1:
                raise ValueError("unrecognized absorption menu cursor")
            return ("\r", "done") if name in selected[0] else ("2", "absorb")
        first, last = reading.details.get("first_label", ""), reading.details.get("last_label", "")
        if not first <= step.keys <= last:
            raise ValueError("absorption slot outside observed labels")
        return step.keys, "done"
    if step.stage == "kind":
        if reading.kind == "command_char" and prompt in TYPE_PROMPTS:
            return ("A" if step.kind == "staff" else "B"), "power"
        if kind_menu_wait(reading, row0, MENU_PROMPTS):
            answer = _wand_menu_answer(lines, 0 if step.kind == "staff" else 1)
            return answer, "power" if answer == "\r" else "kind"
        raise ValueError("unowned Magic-Eater type prompt")
    if step.stage == "power":
        if not _owns_power_prompt(reading):
            raise ValueError("unowned Magic-Eater power prompt")
        staff = step.kind == "staff"
        listed = observed_power_list(lines, "staff" if staff else None)
        if listed is not None:
            operation.magic_eater_power_list = listed
        row = _power_row(lines, step.kind, step.sval)
        if row is None:
            if step.attempts == 0:
                return "*", "power"
            raise ValueError("power missing from observed list")
        label, charges = row
        if not staff:
            operation.magic_eater_wand_charges = charges
        if charges == 0 or any(text in row0 for text in EMPTY):
            if not staff:
                operation.magic_eater_wand_charges = 0
            return "\x1b", "done"
        following = ("target" if step.target else "done") if staff else "aim"
        if label.endswith(")"):
            return label[0], following
        if label in {"》", "> "}:
            return "\r", following
        return "2", "power"
    if step.stage == "target":
        # staff_effect's identify asks for the item (IDENTIFY_ITEM_PROMPT).
        if reading.kind != "item" or not prompt.endswith(IDENTIFY_PROMPTS):
            raise ValueError("unowned Magic-Eater identify prompt")
        if reading.details.get("area") != "inventory" or reading.details.get("menu"):
            raise ValueError("unowned Magic-Eater identify item area")
        first, last = reading.details.get("first_label", ""), reading.details.get("last_label", "")
        if not first <= step.target <= last:
            raise ValueError("identify target outside observed labels")
        return step.target, "done"
    if step.stage == "aim":
        if reading.kind != "direction" or reading.details.get("can_choose_target") is not True:
            raise ValueError("unowned Magic-Eater aim prompt")
        return step.keys, "done"
    raise ValueError("unexpected prompt after Magic-Eater answer")


def advance_magic_eater(executor, screen, match, deadline, outcome):
    operation = executor.active
    if not operation.continuations or not isinstance(operation.continuations[0], MagicEaterStep):
        return None
    step = operation.continuations[0]
    _, messages = read_input_view(screen)
    failed = any(text in line for text in FAILURES for line in messages)
    if failed:
        if any(text in line for text in FAILURES[2:] for line in messages):
            operation.magic_eater_wand_charges = -1
        operation.business_outcome = "failed:magic-eater"
        step = replace(step, stage="done")
        operation.continuations[0] = step
    if match.kind in {ScreenKind.MORE, ScreenKind.LEVEL_UP_STAT}:
        return None
    if match.kind is ScreenKind.COMMAND:
        if step.stage == "done":
            operation.continuations.pop(0)
            return None
    try:
        if step.attempts >= 40:
            raise ValueError("Magic-Eater menu made no progress")
        answer, stage = _answer(step, screen, operation)
        if step.stage == "absorb":
            state = executor._request("state", deadline, map=True)
            before = operation.observation or {}
            old = next((item for item in before.get("inventory", ())
                        if item.get("slot") == step.keys), None)
            current = next((item for item in (state or {}).get("inventory", ())
                            if item.get("slot") == step.keys), None)
            if old is None or current is None or any(
                    old.get(field) != current.get(field)
                    for field in ("tval", "sval", "name", "known", "charges", "count")):
                raise ValueError("absorption item changed")
            executor._bound_state_value = state
        executor._bound_screen_value = screen
        operation.continuations[0] = replace(
            step, stage=stage, attempts=step.attempts + 1 if stage == step.stage else 0)
        return executor._post_and_barrier(answer, deadline, role="answer")
    except ValueError as error:
        reading, _ = read_input_view(screen)
        if ((operation.owner == MISSILE_REASON or step.kind == "staff")
                and _owns_power_prompt(reading)):
            # Missing/unusable powers and bounded menu failures must return to
            # command input before the next policy decision can throw a torch.
            staff = step.kind == "staff"
            listed = observed_power_list(read_input_view(screen)[1],
                                         "staff" if staff else None)
            if listed is not None:
                operation.magic_eater_power_list = listed
            if not staff:
                operation.magic_eater_wand_charges = (
                    -1 if _power_row(read_input_view(screen)[1]) is None else 0)
            operation.continuations[0] = replace(step, stage="done", attempts=0)
            executor._bound_screen_value = screen
            return executor._post_and_barrier("\x1b", deadline, role="answer")
        return executor._terminal(operation, "magic-eater", str(error), match, outcome)
