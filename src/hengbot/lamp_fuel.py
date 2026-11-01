"""What the player knows about the fuel of a worn unidentified lantern.

Owner 2026-10-31 (n1-c life-072, 「直す」): right after descending to Yeek cave
1F the bot poured all five flasks into a burning lantern; every pour was
answered 「ランプに油を注いだ。」「ランプの油は一杯だ。」.  An unidentified
lantern hides its fuel, so the refill rules have to use what the player is
shown instead:

* the game's own reply to a refill.  cmd-refill.cpp do_cmd_refill_lamp clamps
  the fuel to FUEL_LAMP and prints 「ランプの油は一杯だ。」 / "Your lamp is
  full."; from then on the lamp burns at most one fuel per TURNS_PER_TICK game
  turns (object/lite-processor.cpp reduce_lite_life), so the fuel left is at
  least FUEL_LAMP minus the elapsed ticks.
* the game's report that a monster ate the light.  monster-eating.cpp
  process_eat_lite takes 250 + randint1(250) fuel per EAT_LITE blow and,
  unless the player is blind, prints 「明かりが暗くなってしまった。」 /
  "Your light dims."; object/lite-processor.cpp prints 「明かりが消えてしまった！」
  / "Your light has gone out!" when the fuel runs out.  Each dimming lowers
  the least fuel left by the most a blow can take, and the light going out
  leaves none (#47 D57, n1-c life-085: a Super Great Silver Jelly drained the
  lantern dark; the refill of 108,600 game turns earlier still left a known
  floor of about 4,100 fuel, so every refill was refused and the dark walk
  had no recovery).
* whether the lantern still lights the player.  A lantern without fuel adds
  no light radius (specific-object/torch.cpp update_lite_radius), so the
  exported ``light_radius`` drops to 0 unless another source lights, and the
  own grid goes unseen in the dark (``can_see_own_grid``).

Every refill producer reaches an unidentified lantern through
``_light_refill_item`` or ``_unknown_lantern_departure_refill_item``, and both
ask here.
"""

from __future__ import annotations

import re

from hengbot.policy_constants import LANTERN_FULL_FUEL, LANTERN_REFILL_FUEL
from hengbot.town_arbiter import HENGBAND_TURNS_PER_TICK

LAMP_FULL_MESSAGES = frozenset({"ランプの油は一杯だ。", "Your lamp is full."})
LIGHT_DIMS_MESSAGES = frozenset({"明かりが暗くなってしまった。", "Your light dims."})
LIGHT_OUT_MESSAGES = frozenset({"明かりが消えてしまった！", "Your light has gone out!"})
EAT_LITE_MAX_FUEL = 500  # monster-eating.cpp process_eat_lite: 250 + randint1(250)
_MEMORY = "_lamp_full_memory"
_REPEAT_SUFFIX = re.compile(r" <x([1-9]\d*)>$")
_INSCRIPTION = re.compile(r"\s*\{[^{}]*\}\s*$")


def _worn_lantern(snapshot):
    light = next((item for item in snapshot.equipment if item.is_light), None)
    return light if light is not None and light.is_lantern else None


def _lantern_identity(lantern) -> str:
    # The pseudo-ID inscription changes while worn ({並, Q34} -> {高級品, Q34}).
    return _INSCRIPTION.sub("", lantern.name)


def _counted(messages, texts) -> int:
    """How many times the board's messages report one of ``texts``."""
    count = 0
    for message in messages:
        repeat = _REPEAT_SUFFIX.search(message)
        if _REPEAT_SUFFIX.sub("", message) in texts:
            count += int(repeat.group(1)) if repeat else 1
    return count


def observe(policy, snapshot) -> None:
    """Remember the turn of the last 「ランプの油は一杯だ。」 for the worn lantern,
    and the fuel the board's messages say was taken since."""
    lantern = _worn_lantern(snapshot)
    memory = getattr(policy, _MEMORY, None)
    if lantern is None or lantern.known:
        if memory is not None:
            setattr(policy, _MEMORY, None)
        return
    identity = _lantern_identity(lantern)
    if _counted(snapshot.messages, LAMP_FULL_MESSAGES):
        memory = (identity, snapshot.turn, 0)
    elif memory is not None and memory[0] != identity:
        memory = None
    if memory is not None:
        taken = (LANTERN_FULL_FUEL if _counted(snapshot.messages, LIGHT_OUT_MESSAGES)
                 else EAT_LITE_MAX_FUEL * _counted(snapshot.messages, LIGHT_DIMS_MESSAGES))
        memory = (memory[0], memory[1], _taken(memory) + taken)
    setattr(policy, _MEMORY, memory)


def _taken(memory) -> int:
    return memory[2] if len(memory) > 2 else 0


def known_fuel_floor(policy, snapshot) -> int | None:
    """The least fuel the worn unidentified lantern can hold, if known."""
    lantern = _worn_lantern(snapshot)
    memory = getattr(policy, _MEMORY, None)
    if lantern is None or lantern.known or memory is None or memory[0] != _lantern_identity(lantern):
        return None
    burnt = max(0, snapshot.turn - memory[1]) // HENGBAND_TURNS_PER_TICK
    return max(0, LANTERN_FULL_FUEL - burnt - _taken(memory))


def refill_known_unneeded(policy, snapshot) -> bool:
    """Whether the player knows the lantern still holds more than a refill's worth."""
    floor = known_fuel_floor(policy, snapshot)
    return floor is not None and floor > LANTERN_REFILL_FUEL


def unidentified_lantern_out(snapshot) -> bool | None:
    """Whether the player sees the worn lantern no longer lighting them.

    None when the board exports neither light fact (older protocols).
    """
    if snapshot.light_radius is None and snapshot.can_see_own_grid is None:
        return None
    return snapshot.light_radius == 0 or snapshot.can_see_own_grid is False
