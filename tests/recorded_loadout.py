"""Keep ownership replays on the equipment path of their recorded boards.

The captures predate speed-adjusted survival.  Their subsequent boards do not
confirm a new optimizer choice, so measuring ownership after that choice would
measure a fabricated equipment transaction.  This wrapper restores only the
old survival and combat-margin values during a recorded ownership replay,
and the dangerous-field floor they were selected with ("survival >= 95% of
the field maximum", 2026-07-24; production replaced it by the survival / kill
ratio on 2026-10-02).  Without that floor the old values alone moved the tour
capture's index-2 choice from the recorded ★更正せるセオデン王のビークド・アックス set to a
殺戮の野太刀 (9d4) set and broke its sale-path revert proof.
Production optimization and dedicated optimizer tests remain untouched.
"""

from dataclasses import replace
from functools import wraps
from math import isinf
from unittest.mock import patch

import hengbot.equipment_optimizer as optimizer
import hengbot.warrior_loadout_evaluator as evaluator


def recorded_dangerous_field_pool(pool):
    """The recorded-era floor: survival within 95% of the field maximum."""
    max_survival = max(entry.metrics.survival_turns for entry in pool)
    return [entry for entry in pool
            if entry.metrics.survival_turns >= max_survival * 0.95]


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

        with patch.object(evaluator, "_combine_warrior_results", recorded_survival),                 patch.object(optimizer, "_dangerous_field_pool",
                             recorded_dangerous_field_pool):
            return replay(*args, **kwargs)

    return wrapped
