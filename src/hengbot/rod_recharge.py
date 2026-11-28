"""When a held Rod of Detection is ready again: the game's two recharge formulas.

One question, one place (MAINTAINABILITY.md 3): deep_detection_rod waits for the rod it holds and
stationary_bounds bounds that wait; both read the ticks from here.  A tick is a world tick of
``TURNS_PER_TICK`` game turns (world/world-turn-processor.cpp:72-97: process_player_hp_mp and
recharge_magic_items run once every 10 game turns).

* A carried rod (inventory/recharge-processor.cpp:84-103): a zap adds the kind's pval to the
  stack's timeout, and every tick the timeout drops by the number of charging rods of the stack
  (``(timeout + pval - 1) / pval``, at most the stack's number).  So one rod of the stack is
  ready again at most ``pval`` ticks after it went charging, whatever the stack's size.
* An absorbed rod of a Magic-Eater (hpmp/hp-mp-regenerator.cpp:119-159 regenmagic): a cast adds
  ``pval * EATER_ROD_CHARGE`` to the power's charge (cmd-item/cmd-magiceat.cpp:571-572), a power
  of ``count`` rods is usable while the charge is at most ``pval * (count - 1) * EATER_ROD_CHARGE``
  (player-info/magic-eater-data-type.cpp:66-71), and every tick the charge drops by
  ``regen * mult * (count + 10) * EATER_ROD_CHARGE / (30 * 16 * PY_REGEN_NORMAL)`` (integer
  division, :151) with ``mult = 30 + adj_mag_mana[INT]`` (:126-127).  ``regen`` is
  PY_REGEN_NORMAL 197, PY_REGEN_WEAK 98 when weak, PY_REGEN_FAINT 33 or 0 when fainting or
  starving (hpmp/hp-mp-processor.cpp:118,357-365), doubled with Regeneration (:371-373) and
  doubled again while resting (:383-385).  The list shows a rod row as ``charging`` =
  ``ceil(charge / (pval * EATER_ROD_CHARGE))`` of ``count`` (cmd-magiceat.cpp:284-288).

The Rod of Detection is BaseitemDefinitions.jsonc id 375: pval (``parameter_value``) 99.
"""

from __future__ import annotations

from hengbot.recall_wait_reach import TURNS_PER_TICK

# BaseitemDefinitions.jsonc id 375 (Rod of Detection) parameter_value: the recharge a use adds.
DETECTION_ROD_PVAL = 99
# player-info/magic-eater-data-type.h:12.
EATER_ROD_CHARGE = 0x10
# hpmp/hp-mp-regenerator.cpp:126 ``dev``.
EATER_DEV = 30
# hpmp/hp-mp-regenerator.h:8-10.
PY_REGEN_NORMAL = 197
PY_REGEN_WEAK = 98
# hpmp/hp-mp-processor.cpp:383-385: resting doubles the regeneration.
REST_FACTOR = 2
# player/player-status-table.cpp:62-68 adj_mag_mana, indexed by the INT's stat_index.
ADJ_MAG_MANA = (
    0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 5, 6, 7, 8, 9, 10, 11, 11, 12, 12,
    13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
)
# The board's food states and the regeneration they leave (hp-mp-processor.cpp:357-365).  A
# fainting character may be starving (regen 0, never recharging): no bound is read for it.
FOOD_REGEN = {"weak": PY_REGEN_WEAK, "fainting": None}


def carried_ready_ticks(pval: int = DETECTION_ROD_PVAL) -> int:
    """Ticks until a charging carried rod of the stack is ready again, at most."""
    return pval


def regen_amount(food_state: str, *, resting: bool) -> int | None:
    """The tick's ``regen_amount`` for the board's food state (Regeneration not counted: a wait
    read without it is the longer one), None when it may be 0."""
    regen = FOOD_REGEN.get(food_state, PY_REGEN_NORMAL)
    if regen is None:
        return None
    return regen * (REST_FACTOR if resting else 1)


def absorbed_shed_per_tick(count: int, int_index: int, regen: int) -> int:
    """The charge an absorbed rod power of ``count`` rods sheds a tick (regenmagic :151)."""
    index = max(0, min(int_index, len(ADJ_MAG_MANA) - 1))
    mult = EATER_DEV + ADJ_MAG_MANA[index]
    return (regen * mult * (count + 10) * EATER_ROD_CHARGE) // (EATER_DEV * 16 * PY_REGEN_NORMAL)


def absorbed_ready_ticks(count: int, charging: int, int_index: int, regen: int,
                         pval: int = DETECTION_ROD_PVAL) -> int | None:
    """Ticks, at most, from a list showing ``charging`` of ``count`` until one rod of the power is
    usable again, shedding at ``regen``; 0 when one is usable, None when nothing is shed."""
    if count <= 0:
        return None
    # The charge is at most charging * pval * EATER_ROD_CHARGE; usable at (count - 1) of those.
    excess = max(0, charging - (count - 1)) * pval * EATER_ROD_CHARGE
    if excess == 0:
        return 0
    shed = absorbed_shed_per_tick(count, int_index, regen)
    if shed <= 0:
        return None
    return -(-excess // shed)


def game_turns(ticks: int) -> int:
    return ticks * TURNS_PER_TICK
