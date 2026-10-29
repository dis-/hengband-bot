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


@dataclass(frozen=True)
class MagicEaterStep(Continuation):
    stage: str = "kind"
    attempts: int = 0


def compile_magic_eater(key, owner):
    if owner == ABSORB_REASON and re.fullmatch(r"G[a-z]", key):
        return "G", [MagicEaterStep(frozenset(), key[1], stage="absorb")]
    if owner == MISSILE_REASON and re.fullmatch(r"mBp[1-9]", key):
        return "m", [MagicEaterStep(frozenset(), key[-1])]
    if owner in {ABSORB_REASON, MISSILE_REASON}:
        raise ValueError("invalid Magic-Eater operation")
    return None


def _wand_menu_answer(lines):
    choices = [line.strip() for line in lines[2:5]]
    if len(choices) != 3 or not all(
            choice.endswith(names) for choice, names in zip(
                choices, (("杖", "staff"), ("魔法棒", "wand"), ("ロッド", "rod")))):
        raise ValueError("unrecognized Magic-Eater type menu")
    selected = [index for index, choice in enumerate(choices)
                if choice.startswith(("》", ">"))]
    if len(selected) != 1:
        raise ValueError("missing Magic-Eater menu cursor")
    return "\r" if selected[0] == 1 else "2"


def _power_row(lines):
    # Two 40-cell columns. The source prints an ASCII letter or a menu
    # cursor before the baseitem name, then current/max and failure percent.
    pattern = r"(?P<label>[a-z0-9]\)|》|> |  )\s*(?:マジック・ミサイル|Magic Missile)\s+(\d+)\s*/\s*(\d+)\s+\d+%"
    for line in lines[2:20]:
        match = re.search(pattern, line)
        if match:
            return match.group("label"), int(match.group(2))
    return None


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
            return "B", "power"
        # This loop uses raw inkey(), so the server explicitly reports null.
        # Require its complete source-derived menu as well as the null context.
        if reading.source == "null" and row0 in MENU_PROMPTS:
            answer = _wand_menu_answer(lines)
            return answer, "power" if answer == "\r" else "kind"
        raise ValueError("unowned Magic-Eater type prompt")
    if step.stage == "power":
        if not _owns_power_prompt(reading):
            raise ValueError("unowned Magic-Eater power prompt")
        row = _power_row(lines)
        if row is None:
            if step.attempts == 0:
                return "*", "power"
            raise ValueError("Magic Missile missing from observed list")
        label, charges = row
        operation.magic_eater_wand_charges = charges
        if charges == 0 or any(text in row0 for text in EMPTY):
            operation.magic_eater_wand_charges = 0
            return "\x1b", "done"
        if label.endswith(")"):
            return label[0], "aim"
        if label in {"》", "> "}:
            return "\r", "aim"
        return "2", "power"
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
            operation.magic_eater_wand_charges = 0
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
        if operation.owner == MISSILE_REASON and _owns_power_prompt(reading):
            # Missing/unusable powers and bounded menu failures must return to
            # command input before the next policy decision can throw a torch.
            operation.magic_eater_wand_charges = 0
            operation.continuations[0] = replace(step, stage="done", attempts=0)
            executor._bound_screen_value = screen
            return executor._post_and_barrier("\x1b", deadline, role="answer")
        return executor._terminal(operation, "magic-eater", str(error), match, outcome)
