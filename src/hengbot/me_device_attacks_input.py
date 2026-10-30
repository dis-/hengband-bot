"""Executor answers of an absorbed attack power (me_device_attacks).

cmd-magiceat.cpp ``do_cmd_magic_eater``: the kind question (``[A] 杖,
[B] 魔法棒, [C] ロッド:`` or the use_menu 「どの種類の魔法を使いますか？」 menu),
the power prompt and its list, then get_aim_dir for a wand or an aimed rod
(a staff power has no direction).  Each answer is gated on its own observed
prompt.  The list under the power prompt is recorded on the board
(``magic_eater_power_list``); an empty or still-charging power closes the
prompt with ESC (``select_magic_eater`` returns nullopt and the energy is
reset), so a stale remembered row costs no game time.
"""

from dataclasses import dataclass, replace
import re

from hengbot.input_context import read_input_view
from hengbot.input_executor import Continuation, ScreenKind
from hengbot.magic_eater_input import (
    EMPTY, FAILURES, MENU_PROMPTS, TYPE_PROMPTS, _owns_power_prompt, _wand_menu_answer,
    observed_power_list,
)
from hengbot.me_device_attacks import DEVICE_REASON, KIND_LETTER, POWERS


CHARGING = ("その魔法はまだ充填している最中だ。", "The magic is still charging.")
_KINDS = ("staff", "wand", "rod")


@dataclass(frozen=True)
class DeviceStep(Continuation):
    kind: str = "wand"
    sval: int = 15
    stage: str = "kind"
    attempts: int = 0


_KEY = re.compile(r"m(?P<kind>[ABC])(?P<letter>[a-z0-9])(?P<direction>[1-9]?)")


def compile_device(key, owner):
    if owner != DEVICE_REASON:
        return None
    match = _KEY.fullmatch(key)
    if match is None:
        raise ValueError("invalid Magic-Eater device attack")
    kind = next(kind for kind, letter in KIND_LETTER.items() if letter == match["kind"])
    letter = match["letter"]
    sval = ord(letter) - ord("a") if letter.isalpha() else int(letter) + 26
    power = POWERS.get((kind, sval))
    if power is None or power.aimed != bool(match["direction"]):
        raise ValueError("invalid Magic-Eater device attack")
    return "m", [DeviceStep(frozenset(), match["direction"], kind=kind, sval=sval)]


def _row(lines, power):
    """(label, usable) of the power's displayed row, else None."""
    names = "|".join(re.escape(name) for name in power.names)
    if power.kind == "rod":
        # " {:<22} 充填:{:2}/{:2}{:3}%" / " {:<22}   ({:2}/{:2}) {:3}%": c of n charging.
        counts = r"(?:充填:\s*|\(\s*)(?P<first>\d+)\s*/\s*(?P<second>\d+)\)?\s*\d+%"
    else:
        counts = r"(?P<first>\d+)\s*/\s*(?P<second>\d+)\s+\d+%"
    pattern = r"(?P<label>[a-z0-9]\)|》|> |  )\s*(?:" + names + r")\s+" + counts
    for line in lines[2:20]:
        match = re.search(pattern, line)
        if match:
            first, second = int(match["first"]), int(match["second"])
            return match["label"], (first < second if power.kind == "rod" else first > 0)
    return None


def _answer(step, reading, lines, operation):
    prompt = reading.prompt.rstrip()
    row0 = lines[0].strip() if lines else ""
    power = POWERS[(step.kind, step.sval)]
    if step.stage == "kind":
        if reading.kind == "command_char" and prompt in TYPE_PROMPTS:
            return KIND_LETTER[step.kind], "power"
        if reading.source == "null" and row0 in MENU_PROMPTS:
            answer = _wand_menu_answer(lines, _KINDS.index(step.kind))
            return answer, "power" if answer == "\r" else "kind"
        raise ValueError("unowned Magic-Eater type prompt")
    if step.stage == "power":
        if not _owns_power_prompt(reading):
            raise ValueError("unowned Magic-Eater power prompt")
        listed = observed_power_list(lines, step.kind)
        if listed is not None:
            operation.magic_eater_power_list = listed
        row = _row(lines, power)
        if row is None:
            if step.attempts == 0:
                return "*", "power"
            raise ValueError("power missing from observed list")
        label, usable = row
        if not usable or any(text in row0 for text in (*EMPTY, *CHARGING)):
            return "\x1b", "done"
        following = "aim" if power.aimed else "done"
        if label.endswith(")"):
            return label[0], following
        if label in {"》", "> "}:
            return "\r", following
        return "2", "power"
    if step.stage == "aim":
        if reading.kind != "direction" or reading.details.get("can_choose_target") is not True:
            raise ValueError("unowned Magic-Eater aim prompt")
        return step.keys, "done"
    raise ValueError("unexpected prompt after Magic-Eater device answer")


def advance_device(executor, screen, match, deadline, outcome):
    operation = executor.active
    if not operation.continuations or not isinstance(operation.continuations[0], DeviceStep):
        return None
    step = operation.continuations[0]
    reading, lines = read_input_view(screen)
    if any(text in line for text in FAILURES for line in lines):
        if any(text in line for text in FAILURES[2:] for line in lines):
            # The game's own answer for a kind with nothing absorbed.
            operation.magic_eater_power_list = {"kind": step.kind, "rows": []}
        operation.business_outcome = "failed:magic-eater"
        step = replace(step, stage="done")
        operation.continuations[0] = step
    if match.kind in {ScreenKind.MORE, ScreenKind.LEVEL_UP_STAT}:
        return None
    if match.kind is ScreenKind.COMMAND and step.stage == "done":
        operation.continuations.pop(0)
        return None
    try:
        if step.attempts >= 40:
            raise ValueError("Magic-Eater device menu made no progress")
        answer, stage = _answer(step, reading, lines, operation)
    except ValueError as error:
        if _owns_power_prompt(reading):
            # A missing power or a bounded menu failure returns to command
            # input before the next decision (the list is kept on the board).
            listed = observed_power_list(lines, step.kind)
            if listed is not None:
                operation.magic_eater_power_list = listed
            operation.continuations[0] = replace(step, stage="done", attempts=0)
            executor._bound_screen_value = screen
            return executor._post_and_barrier("\x1b", deadline, role="answer")
        return executor._terminal(operation, "magic-eater-device", str(error), match, outcome)
    executor._bound_screen_value = screen
    operation.continuations[0] = replace(
        step, stage=stage, attempts=step.attempts + 1 if stage == step.stage else 0)
    return executor._post_and_barrier(answer, deadline, role="answer")
