"""Keep ownership replays on the equipment path of their recorded boards.

The captures predate speed-adjusted survival.  Their subsequent boards do not
confirm a new optimizer choice, so measuring ownership after that choice would
measure a fabricated equipment transaction.  This wrapper restores only the
old survival and combat-margin values during a recorded ownership replay.
Production optimization and dedicated optimizer tests remain untouched.
"""

from dataclasses import replace
from functools import wraps
from math import isinf
from unittest.mock import patch

import hengbot.warrior_loadout_evaluator as evaluator


def recorded_loadout_replay(replay):
    """Run a new-code ownership measurement with the recorded gear choice."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        original = evaluator._combine_warrior_results

        def recorded_survival(loadout, inputs, melee, defense, ranged):
            result = original(loadout, inputs, melee, defense, ranged)
            incoming = (defense.expected_melee_damage
                        + ranged.expected_ranged_damage)
            hp = evaluator.loadout_max_hp(loadout, inputs)
            survival = hp / incoming if incoming > 0 else float("inf")
            kill = melee.expected_kill_turns
            if isinf(kill):
                margin = -float("inf")
            elif isinf(survival):
                margin = float("inf")
            else:
                margin = survival - kill
            return replace(result, metrics=replace(
                result.metrics, survival_turns=survival, combat_margin=margin,
            ))

        with patch.object(evaluator, "_combine_warrior_results", recorded_survival):
            return replay(*args, **kwargs)

    return wrapped
