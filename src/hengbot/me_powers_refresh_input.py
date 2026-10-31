"""Executor answers of the turn-free Magic-Eater list refresh (me_powers_refresh).

cmd-magiceat.cpp ``select_magic_eater(only_browse=true)``: the kind question
(``[A] 杖, [B] 魔法棒, [C] ロッド:`` or the use_menu 「どの種類の魔法を見ますか？」
menu), the browse prompt and its list, ESC back to command input.
"""

from dataclasses import dataclass, replace
import re

from hengbot.input_executor import Continuation, ScreenKind
from hengbot.input_context import read_input_view
from hengbot.magic_eater_input import (
    TYPE_PROMPTS, _wand_menu_answer, kind_menu_wait, observed_power_list,
)
from hengbot.me_powers_refresh import BROWSE_REASONS, KIND_LETTER, KINDS


BROWSE_PROMPTS = ("('*'で一覧, ESCで中断) どの魔力を見ますか？",
                  "(*=List, ESC=exit) Browse which power?")
BROWSE_MENU_PROMPTS = ("どの種類の魔法を見ますか？", "Which type of magic do you browse?")
NOT_ABSORBED = ("その種類の魔法は覚えていない！", "You don't have that type of magic!")


@dataclass(frozen=True)
class BrowseStep(Continuation):
    kind: str = "wand"
    stage: str = "kind"
    attempts: int = 0


def compile_refresh(key, owner):
    if owner not in BROWSE_REASONS:
        return None
    match = re.fullmatch(r"b([ABC])", key)
    if match is None:
        raise ValueError("invalid Magic-Eater browse refresh")
    kind = next(kind for kind, letter in KIND_LETTER.items() if letter == match[1])
    return "b", [BrowseStep(frozenset(), "", kind=kind)]


def _browse_answer(step, reading, lines, operation):
    prompt = reading.prompt.rstrip()
    row0 = lines[0].strip() if lines else ""
    if step.stage == "kind":
        if reading.kind == "command_char" and prompt in TYPE_PROMPTS:
            return KIND_LETTER[step.kind], "list"
        if kind_menu_wait(reading, row0, BROWSE_MENU_PROMPTS):
            answer = _wand_menu_answer(lines, KINDS.index(step.kind))
            return answer, "list" if answer == "\r" else "kind"
    elif reading.kind in {"spell", "command_char"} and prompt in BROWSE_PROMPTS:
        listed = observed_power_list(lines, step.kind)
        if listed is not None:
            operation.magic_eater_power_list = listed
            return "\x1b", "done"
        if step.stage == "list" and step.attempts == 0:
            # always_show_list off: '*' shows the list under the same prompt.
            return "*", "list"
        return "\x1b", "done"
    raise ValueError("unowned Magic-Eater browse prompt")


def advance_refresh(executor, screen, match, deadline, outcome):
    operation = executor.active
    if not operation.continuations or not isinstance(operation.continuations[0], BrowseStep):
        return None
    step = operation.continuations[0]
    if match.kind in {ScreenKind.MORE, ScreenKind.LEVEL_UP_STAT}:
        return None
    reading, lines = read_input_view(screen)
    if match.kind is ScreenKind.COMMAND:
        if any(text in line for text in NOT_ABSORBED for line in lines):
            # The game's own answer for a kind with nothing absorbed.
            operation.magic_eater_power_list = {"kind": step.kind, "rows": []}
        elif step.stage != "done":
            operation.business_outcome = "failed:magic-eater-browse"
        operation.continuations.pop(0)
        return None
    try:
        if step.attempts >= 6:
            raise ValueError("Magic-Eater browse made no progress")
        answer, stage = _browse_answer(step, reading, lines, operation)
    except ValueError as error:
        return executor._terminal(operation, "magic-eater-browse", str(error), match, outcome)
    executor._bound_screen_value = screen
    operation.continuations[0] = replace(
        step, stage=stage, attempts=step.attempts + 1 if stage == step.stage else 0)
    return executor._post_and_barrier(answer, deadline, role="answer")
