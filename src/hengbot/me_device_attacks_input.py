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

from dataclasses import dataclass
import re

from hengbot.input_executor import Continuation
from hengbot.me_device_attacks import DEVICE_REASON, POWERS, TARGETABLE_SHAPES
from hengbot.me_menu import MagicEaterMenu
from hengbot.policy_constants import DIRECTION_KEYS
from hengbot import me_absorbed_substitutes, me_powers
from hengbot.me_powerful_activation import RACIAL_KEY


@dataclass(frozen=True)
class DeviceStep(Continuation):
    kind: str = "wand"
    sval: int = 15
    stage: str = "kind"
    attempts: int = 0
    goal: tuple[int, int] | None = None   # the burst grid (y, x) of a targeted ball


_KEY = re.compile(r"m(?P<kind>[ABC])(?P<letter>[a-z0-9])"
                  r"(?:(?P<direction>[1-9])|@(?P<y>\d+),(?P<x>\d+))?")


def _owns_utility_reason(owner):
    return isinstance(owner, str) and owner.startswith(me_powers.REASON + ":")


def _tables():
    """Who may send a device key, and the powers each may name: the attack table,
    the utility table (me_powers) and a quest's absorbed-power substitutes.  A
    power's row is looked up in this order, whichever table admitted its key."""
    return ((lambda owner: owner == DEVICE_REASON, POWERS),
            (_owns_utility_reason, me_powers.BY_KEY),
            (me_absorbed_substitutes.owns, me_absorbed_substitutes.POWERS))


def _table(owner):
    return next((table for owns, table in _tables() if owns(owner)), None)


def _power(kind, sval):
    for _, table in _tables():
        if (kind, sval) in table:
            return table[(kind, sval)]
    raise KeyError((kind, sval))


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


class DeviceMenu(MagicEaterMenu):
    step_type = DeviceStep
    compile = staticmethod(compile_device)
    terminal_name = "magic-eater-device"
    stall_text = "Magic-Eater device menu made no progress"
    unexpected_text = "unexpected prompt after Magic-Eater device answer"
    unasked_stages = frozenset({"aim", "target"})

    def _aim_or_target_stage(self, step, seen, operation):
        answer = self.aim_stage(step, seen, operation)
        return answer if step.goal is None else ("*", "target")

    def _target_stage(self, step, seen, operation):
        """One key of the cursor walk to the burst grid, from the published cursor."""
        details = seen.reading.details
        if seen.reading.kind != "target" or details.get("look") is not False:
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

    stages = {"kind": MagicEaterMenu.kind_stage,
              "power": MagicEaterMenu.power_stage,
              "aim": _aim_or_target_stage,
              "target": _target_stage}

    def power_of(self, step):
        return _power(step.kind, step.sval)

    def after_power(self, step):
        return "aim" if self.power_of(step).aimed else "done"


DEVICE_USE = DeviceMenu()
