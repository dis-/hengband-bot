"""Executor answers of the Magic-Eater's Powerful Activation (me_powerful_activation).

``U`` opens the racial power prompt (cmd-action/cmd-racial.cpp
``racial_power_make_prompt``: 「(特殊能力 a-c, '*'で一覧, '/'で閲覧, ESCで中断)
どの能力を使いますか？」, its list rows "x) name  Lv MP 失率", asked with
input_spell_choice, input_context kind spell), then
``do_cmd_magic_eater(player, false, true)`` asks the same kind question and
power list as an ordinary absorbed use (cmd-item/cmd-magiceat.cpp), and the
Perception power's identify_fully asks 「どのアイテムを*鑑定*しますか? 」 and
shows screen_object (spell-kind/spells-perception.cpp).  Every answer is gated
on its own observed prompt; the racial letter and the power letter are read
from the displayed lists.  A power the list shows empty is cancelled with ESC
(``do_cmd_magic_eater`` returns false, so no hit points are paid).
"""

from dataclasses import dataclass, replace
import re

from hengbot.input_context import read_input_view
from hengbot.input_executor import Continuation, ScreenKind
from hengbot.magic_eater_input import (
    EMPTY, FAILURES, LIST_CHOICE_KINDS, MENU_PROMPTS, TYPE_PROMPTS, _owns_power_prompt,
    _wand_menu_answer, kind_menu_wait, observed_power_list,
)
from hengbot.me_device_attacks_input import _KINDS, CHARGING, _row
from hengbot import me_powerful_activation as powerful
from hengbot import me_powers


RACIAL_PROMPT = re.compile(
    r"\(特殊能力 [a-z0-9]-[a-z0-9], '\*'で一覧, '/'で閲覧, ESCで中断\) どの能力を使いますか？"
    r"|\(Powers [a-z0-9]-[a-z0-9], \*=List, /=Browse, ESC=exit\) Use which power\?")
POWER_NAME = ("強力発動", "Powerful Activation")
_RACIAL_ROW = re.compile(
    r"(?P<label>[a-z0-9]\)|》|>)?\s*(?:" + "|".join(map(re.escape, POWER_NAME))
    + r")\s+\d+\s+\d+\s+\d+%")
FULL_IDENTIFY_PROMPTS = ("どのアイテムを*鑑定*しますか?", "*Identify* which item?")
_KEY = re.compile(r"U(?P<kind>[ABC])(?P<letter>[a-z0-9])(?P<target>(?:/?[a-w])?)")


@dataclass(frozen=True)
class PowerfulStep(Continuation):
    sval: int = 5
    kind: str = "staff"
    target: str = ""
    stage: str = "racial"
    attempts: int = 0


def compile_powerful(key, owner):
    match = _KEY.fullmatch(key)
    if match is None:
        return None
    effect = powerful.activatable(me_powers.kind_of(match["kind"]),
                                  me_powers.decode_letter(match["letter"]))
    if effect is None or effect.targeted != bool(match["target"]):
        raise ValueError("invalid Magic-Eater powerful activation")
    return powerful.RACIAL_KEY, [PowerfulStep(frozenset(), "", sval=effect.sval,
                                              kind=effect.kind, target=match["target"])]


def _owns_racial_prompt(reading):
    """racial_power_process_input asks with input_spell_choice (kind spell).

    #47 n1-c lives 072-076: the gate accepted only command_char, so the
    published spell wait was refused and left open (stuck-prompt).
    """
    return (reading.kind in LIST_CHOICE_KINDS
            and RACIAL_PROMPT.fullmatch(reading.prompt.strip()) is not None)


def _racial_answer(reading, lines):
    if not _owns_racial_prompt(reading):
        raise ValueError("unowned racial power prompt")
    for line in lines[1:20]:
        row = _RACIAL_ROW.search(line)
        if row is not None:
            label = row["label"]
            if label is None:
                return "2"  # use_menu: the cursor is on another row
            return label[0] if label.endswith(")") else "\r"
    return None


def _target_answer(step, reading):
    if reading.kind != "item" or not reading.prompt.rstrip().endswith(FULL_IDENTIFY_PROMPTS):
        raise ValueError("unowned *Identify* prompt")
    details = reading.details
    wanted = "equipment" if step.target.startswith("/") else "inventory"
    if details.get("menu"):
        raise ValueError("unowned *Identify* item menu")
    if details.get("area") != wanted:
        if wanted in details.get("areas", ()):
            return "/", "target"
        raise ValueError("*Identify* target area not offered")
    letter = step.target[-1]
    if not details.get("first_label", "") <= letter <= details.get("last_label", ""):
        raise ValueError("*Identify* target outside observed labels")
    return letter, "viewer"


def _answer(step, reading, lines, operation):
    effect = powerful.activatable(step.kind, step.sval)
    row0 = lines[0].strip() if lines else ""
    if step.stage == "racial":
        answer = _racial_answer(reading, lines)
        if answer is None:
            if step.attempts == 0:
                return "*", "racial"
            raise ValueError("Powerful Activation missing from the power list")
        return answer, "kind" if answer != "2" else "racial"
    if step.stage == "kind":
        if reading.kind == "command_char" and reading.prompt.rstrip() in TYPE_PROMPTS:
            return me_powers.KIND_LETTER[effect.kind], "power"
        if kind_menu_wait(reading, row0, MENU_PROMPTS):
            answer = _wand_menu_answer(lines, _KINDS.index(effect.kind))
            return answer, "power" if answer == "\r" else "kind"
        raise ValueError("unowned Magic-Eater type prompt")
    if step.stage == "power":
        if not _owns_power_prompt(reading):
            raise ValueError("unowned Magic-Eater power prompt")
        listed = observed_power_list(lines, effect.kind)
        if listed is not None:
            operation.magic_eater_power_list = listed
        row = _row(lines, effect)
        if row is None:
            if step.attempts == 0:
                return "*", "power"
            raise ValueError("power missing from observed list")
        label, usable = row
        if not usable or any(text in row0 for text in (*EMPTY, *CHARGING)):
            return "\x1b", "done"
        following = "target" if effect.targeted else "done"
        if label.endswith(")"):
            return label[0], following
        if label in {"》", "> "}:
            return "\r", following
        return "2", "power"
    if step.stage == "target":
        return _target_answer(step, reading)
    raise ValueError("unexpected prompt after Powerful Activation answer")


def _viewer_answer(match):
    """screen_object's pages: a space per page, ESC on the last one."""
    if match.kind is ScreenKind.IDENTIFY_VIEWER_PAGE:
        return " ", "viewer"
    if match.kind is ScreenKind.IDENTIFY_VIEWER_FINAL:
        return "\x1b", "done"
    return None


def advance_powerful(executor, screen, match, deadline, outcome):
    operation = executor.active
    if not operation.continuations or not isinstance(operation.continuations[0], PowerfulStep):
        return None
    step = operation.continuations[0]
    reading, lines = read_input_view(screen)
    if any(text in line for text in FAILURES for line in lines):
        operation.business_outcome = "failed:magic-eater"
        step = replace(step, stage="done")
        operation.continuations[0] = step
    if match.kind in {ScreenKind.MORE, ScreenKind.LEVEL_UP_STAT}:
        return None
    if match.kind is ScreenKind.COMMAND and step.stage in {"done", "viewer"}:
        operation.continuations.pop(0)
        return None
    try:
        if step.attempts >= 40:
            raise ValueError("Powerful Activation menu made no progress")
        viewer = _viewer_answer(match) if step.stage == "viewer" else None
        answer, stage = viewer or _answer(step, reading, lines, operation)
    except ValueError as error:
        if _owns_power_prompt(reading) or _owns_racial_prompt(reading):
            # A missing or empty power returns to command input before the
            # next decision; the list is kept on the board.
            listed = observed_power_list(lines, step.kind)
            if listed is not None and _owns_power_prompt(reading):
                operation.magic_eater_power_list = listed
            operation.continuations[0] = replace(step, stage="done", attempts=0)
            executor._bound_screen_value = screen
            return executor._post_and_barrier("\x1b", deadline, role="answer")
        return executor._terminal(operation, "magic-eater-powerful", str(error), match, outcome)
    executor._bound_screen_value = screen
    operation.continuations[0] = replace(
        step, stage=stage, attempts=step.attempts + 1 if stage == step.stage else 0)
    return executor._post_and_barrier(answer, deadline, role="answer")
