"""Whether the player's haste is on: the one reader of the speed field.

The field (main-window-stat-poster.cpp print_speed; the board's speed_display carries the same colour,
bot-json-output.cpp make_speed_display_json) is yellow for fast and not slow, violet for slow and not
fast, and the plain colour for neither AND for both: haste +10 and slowness -10 add up to the player's
own speed, so neither the colour nor the value tells those two apart.  n1-b life-312 (turn 11651908):
a shattered Potion of Slowness turned 加速(+13) yellow to 加速(+3) light green with the haste still on, and
four Potions of Speed went down in a row, none printing 「素早く動けるようになった！」.

What tells them apart is what the game printed on the way there (set_acceleration, buff-setter.cpp;
set_deceleration, bad-status-setter.cpp), so the two effects are followed from board to board and the
colour corrects them whenever it is sure.  A plain colour is "both" only when both are followed as on;
otherwise it is neither.  Nothing is guessed: with no line (a fresh process, a restored checkpoint) the
plain colour reads as neither, as it did before.  While riding the field is the mount's.

Pickled checkpoints have no ``MEMORY`` attribute: it is created on first use.
"""

from __future__ import annotations

from dataclasses import dataclass

MEMORY = "_haste_read_memory"
HASTE_ON = frozenset({"素早く動けるようになった！", "You feel yourself moving much faster!"})
HASTE_OFF = frozenset({"動きの素早さがなくなったようだ。", "You feel yourself slow down."})
SLOW_ON = frozenset({"体の動きが遅くなってしまった！", "You feel yourself moving slower!"})
SLOW_OFF = frozenset({"動きの遅さがなくなったようだ。", "You feel yourself speed up."})
_YELLOW, _VIOLET = "yellow", "violet"


@dataclass
class Memory:
    board: tuple | None = None  # the last board read: a redraw is not read twice
    fast: bool = False
    slow: bool = False


def _memory(policy) -> Memory:
    memory = getattr(policy, MEMORY, None)
    if memory is None:
        memory = Memory()
        setattr(policy, MEMORY, memory)
    return memory


def _own_field(snapshot) -> tuple | None:
    display = snapshot.player.speed_display
    return None if display is None or display[3] else display


def observe(policy, snapshot) -> None:
    """Every decision: this board's lines, then what its colour is sure of."""
    memory = _memory(policy)
    board = (snapshot.turn, snapshot.messages)
    if board == memory.board:
        return
    memory.board = board
    for line in snapshot.messages:  # the game prints each only on a change, so no <xN>
        if line in HASTE_ON or line in HASTE_OFF:
            memory.fast = line in HASTE_ON
        elif line in SLOW_ON or line in SLOW_OFF:
            memory.slow = line in SLOW_ON
    display = _own_field(snapshot)
    colour = None if display is None else display[2]
    if colour in {_YELLOW, _VIOLET}:
        memory.fast, memory.slow = colour == _YELLOW, colour == _VIOLET
    elif not (memory.fast and memory.slow):
        memory.fast = memory.slow = False


def adds_speed(snapshot) -> bool:
    """The field shows haste counted in ``player.speed``: on and not cancelled by slowness."""
    display = _own_field(snapshot)
    return display is not None and display[2] == _YELLOW


def hasted(policy, snapshot) -> bool:
    """The haste is on, cancelled by slowness or not.  At a displayed speed of exactly +0 the field is
    blank, so haste with nothing else there is not observable."""
    display = _own_field(snapshot)
    if display is None or display[2] == _VIOLET:
        return False
    return display[2] == _YELLOW or _memory(policy).fast
