"""The one place a return to town starts (the ``_returning_to_town`` latch and its trigger).

Whole-bot maintainability review 2026-11-17 (N6): "a return to town starts here" was written by
hand as ``_note_return_start(trigger)`` / ``_returning_to_town = True`` /
``_last_return_trigger = trigger`` at about fifty sites in fifteen modules.  Every site now calls
one of the functions below; ``scripts/return_start_lint.py`` fails on a latch or trigger write
outside them (a reset to False / None stays where it is).

- ``start(policy, trigger)``: the town hold's note, then the latch, then -- when ``trigger`` is
  not None -- the trigger.  ``start(policy)`` (no trigger) leaves ``_last_return_trigger`` as it
  was, as the sites that noted ``None`` always did.
- ``relatch(policy)``: re-assert the latch with the trigger already recorded (the fundraising
  emergency teleports re-latch an income run's return without a trigger of their own).
- ``set_trigger(policy, trigger)``: record why a return is (or would be) wanted without latching
  it (the town-return chooser records the condition; the return's own rung latches it).
"""

from __future__ import annotations


def start(policy, trigger: str | None = None) -> None:
    """A return to town starts: note it for the town hold, latch it and record its trigger."""
    policy._note_return_start(trigger)
    policy._returning_to_town = True
    if trigger is not None:
        policy._last_return_trigger = trigger


def relatch(policy) -> None:
    """Re-assert the return latch under the trigger already recorded (no trigger write)."""
    policy._note_return_start(policy._last_return_trigger)
    policy._returning_to_town = True


def set_trigger(policy, trigger: str) -> None:
    """Record why the return is wanted without latching it."""
    policy._last_return_trigger = trigger
