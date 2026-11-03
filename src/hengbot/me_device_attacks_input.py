"""Executor answers of an absorbed attack power (me_device_attacks).

cmd-magiceat.cpp ``do_cmd_magic_eater``: the kind question (``[A] 杖,
[B] 魔法棒, [C] ロッド:`` or the use_menu 「どの種類の魔法を使いますか？」 menu),
the power prompt and its list, then get_aim_dir for a wand or an aimed rod
(a staff power has no direction).  A ball or breath burst on a grid
(``m`` + kind + power + ``@y,x``, me_device_attacks.device_target_key)
answers get_aim_dir with ``*`` (target-getter.cpp:89-97 target_set), then
each target prompt from its published cursor: ``p`` leaves the monster mode
for the free mode at the player (target-setter.cpp:322-329), a direction key
moves the cursor one grid (:523-530, decide_change_panel :534) and ``t`` at the
grid makes it the target (:482-487); get_aim_dir then fires at it.  Each
answer is gated on its own observed prompt.  The list under the power prompt is recorded on the board
(``magic_eater_power_list``); an empty or still-charging power closes the
prompt with ESC (``select_magic_eater`` returns nullopt and the energy is
reset), so a stale remembered row costs no game time.  The utility powers
(me_powers, reasons ``me-power:...``) and a quest's absorbed-power
substitutes (me_absorbed_substitutes, reasons ending ``:absorbed-power``) are
answered the same way.
"""

from dataclasses import dataclass, replace
import re

from hengbot.input_context import read_input_view
from hengbot.input_executor import Continuation, ScreenKind
from hengbot.magic_eater_input import (
    EMPTY, FAILURES, MENU_PROMPTS, TYPE_PROMPTS, _owns_power_prompt, _wand_menu_answer,
    aim_never_asked, kind_menu_wait, observed_power_list,
)
from hengbot.me_device_attacks import DEVICE_REASON, POWERS, TARGETABLE_SHAPES
from hengbot.policy_constants import DIRECTION_KEYS
from hengbot import me_absorbed_substitutes, me_powers
from hengbot.me_powerful_activation import RACIAL_KEY


CHARGING = ("その魔法はまだ充填している最中だ。", "The magic is still charging.")
_KINDS = ("staff", "wand", "rod")


@dataclass(frozen=True)
class DeviceStep(Continuation):
    kind: str = "wand"
    sval: int = 15
    stage: str = "kind"
    attempts: int = 0
    goal: tuple[int, int] | None = None   # the burst grid (y, x) of a targeted ball


_KEY = re.compile(r"m(?P<kind>[ABC])(?P<letter>[a-z0-9])"
                  r"(?:(?P<direction>[1-9])|@(?P<y>\d+),(?P<x>\d+))?")


def _table(owner):
    """The attack table, the utility table (me_powers) for its reasons, or a
    quest's absorbed-power substitutes (me_absorbed_substitutes) for theirs."""
    if owner == DEVICE_REASON:
        return POWERS
    if isinstance(owner, str) and owner.startswith(me_powers.REASON + ":"):
        return me_powers.BY_KEY
    if me_absorbed_substitutes.owns(owner):
        return me_absorbed_substitutes.POWERS
    return None


def _power(kind, sval):
    return (POWERS.get((kind, sval)) or me_powers.BY_KEY.get((kind, sval))
            or me_absorbed_substitutes.POWERS[(kind, sval)])


def compile_device(key, owner):
    table = _table(owner)
    if table is None or key.startswith(RACIAL_KEY):
        # A utility power cast by Powerful Activation (me_powerful_activation_input).
        return None
    match = _KEY.fullmatch(key)
    if match is None:
        raise ValueError("invalid Magic-Eater device attack")
    kind, sval = me_powers.kind_of(match["kind"]), me_powers.decode_letter(match["letter"])
    power = table.get((kind, sval))
    goal = (int(match["y"]), int(match["x"])) if match["y"] is not None else None
    if power is None or power.aimed != bool(match["direction"] or goal):
        raise ValueError("invalid Magic-Eater device attack")
    if goal is not None and getattr(power, "shape", None) not in TARGETABLE_SHAPES:
        raise ValueError("only a ball or a breath bursts on a target grid")
    return "m", [DeviceStep(frozenset(), match["direction"] or "", kind=kind, sval=sval, goal=goal)]


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
    power = _power(step.kind, step.sval)
    if step.stage == "kind":
        if reading.kind == "command_char" and prompt in TYPE_PROMPTS:
            return me_powers.KIND_LETTER[step.kind], "power"
        if kind_menu_wait(reading, row0, MENU_PROMPTS):
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
        if step.goal is not None:
            return "*", "target"
        return step.keys, "done"
    if step.stage == "target":
        return _target_answer(step, reading)
    raise ValueError("unexpected prompt after Magic-Eater device answer")


def _target_answer(step, reading):
    """One key of the cursor walk to the burst grid, from the published cursor."""
    details = reading.details
    if reading.kind != "target" or details.get("look") is not False:
        raise ValueError("unowned Magic-Eater target prompt")
    if details.get("free") is not True:
        return "p", "target"
    cursor = (details.get("y"), details.get("x"))
    if not all(isinstance(value, int) for value in cursor):
        raise ValueError("target cursor not published")
    if cursor == step.goal:
        return "t", "done"
    dy, dx = (step.goal[0] - cursor[0], step.goal[1] - cursor[1])
    return DIRECTION_KEYS[((dy > 0) - (dy < 0), (dx > 0) - (dx < 0))], "target"


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
    if aim_never_asked(step, match) or (match.kind is ScreenKind.COMMAND and step.stage == "target"):
        operation.business_outcome = "failed:magic-eater"
        step = replace(step, stage="done")
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
