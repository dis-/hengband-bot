"""Keep recorded replays on the equipment path of their recorded boards.

Three declared walls; production optimization and dedicated optimizer tests
remain untouched.

``recorded_loadout_replay``: the captures predate speed-adjusted survival.
Their subsequent boards do not confirm a new optimizer choice, so measuring
ownership after that choice would measure a fabricated equipment transaction.
This wrapper restores the old survival and combat-margin values during a
recorded ownership replay, and the selection rule they were chosen with.

``pre_ratio_optimizer_rule`` / ``pre_ratio_optimizer_replay``: replays whose
subject is not equipment selection and that were recorded (or last pinned)
under the pre-2026-10-02 rule keep today's survival but compare loadouts as
before the user decisions 「生存÷撃破の比で比べる」 and 「足切りも比に置き換える」:
combat margin = survival - kill turns, and a dangerous field (no loadout
survives SUFFICIENT_SURVIVAL_TURNS) keeps "survival >= 95% of the field
maximum" (2026-07-24).  Without the floor the tour capture's index-2 choice
moved from the recorded ★更正せるセオデン王のビークド・アックス set to a
殺戮の野太刀 (9d4) set and broke its sale-path revert proof.  Replays whose
subject IS an equipment choice pin the new divergence instead.

``pre_light_radius_rule`` / ``pre_light_radius_replay``: replays whose subject
is not the light (equipment) choice and that were recorded under the light
comparison before the user decision 「照らせる範囲も比べる」 (2026-10-19, #86)
compare permanent lights by ``light_source_quality`` only, as before: the
radius term of ``_prefer`` and ``_stable_operational_best`` is 0.  Without it
the tour character's worn フェアノールのランプ (radius 2) is replaced by the
Home ★ガラドリエルの玻璃瓶 (radius 3) on its first Home board, a transaction
the recorded boards never confirm.  Replays whose subject IS the light choice
pin the new divergence instead.  The walls compose: a replay may need this
one and ``pre_ratio_optimizer_replay`` / ``recorded_loadout_replay``.
"""

from contextlib import ExitStack, contextmanager
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


def _difference_margin(survival, kill):
    if isinf(kill):
        return -float("inf")
    if isinf(survival):
        return float("inf")
    return survival - kill


@contextmanager
def pre_ratio_optimizer_rule(*, recorded_survival=False):
    """Compare loadouts by the pre-2026-10-02 rule (see the module text).

    ``recorded_survival`` also restores the survival of the captures that
    predate speed-adjusted survival (``recorded_loadout_replay``).
    """
    original = evaluator._combine_warrior_results

    def combine(loadout, inputs, melee, defense, ranged):
        result = original(loadout, inputs, melee, defense, ranged)
        survival = result.metrics.survival_turns
        if recorded_survival:
            incoming = (defense.expected_melee_damage
                        + ranged.expected_ranged_damage)
            hp = evaluator.loadout_max_hp(loadout, inputs)
            survival = hp / incoming if incoming > 0 else float("inf")
        margin = _difference_margin(survival, melee.expected_kill_turns)
        return replace(result, metrics=replace(
            result.metrics, survival_turns=survival, combat_margin=margin,
        ))

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(evaluator, "_combine_warrior_results", combine))
        stack.enter_context(patch.object(
            optimizer, "_dangerous_field_pool", recorded_dangerous_field_pool))
        yield


def pre_ratio_optimizer_replay(replay):
    """Run ``replay`` under ``pre_ratio_optimizer_rule`` (today's survival)."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_ratio_optimizer_rule():
            return replay(*args, **kwargs)

    return wrapped


def recorded_loadout_replay(replay):
    """Run a new-code ownership measurement with the recorded gear choice."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_ratio_optimizer_rule(recorded_survival=True):
            return replay(*args, **kwargs)

    return wrapped


@contextmanager
def pre_light_radius_rule():
    """Compare permanent lights as before 2026-10-19 (see the module text)."""
    with patch.object(optimizer, "permanent_light_radius", lambda _item: 0):
        yield


def pre_light_radius_replay(replay):
    """Run ``replay`` under ``pre_light_radius_rule``."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_light_radius_rule():
            return replay(*args, **kwargs)

    return wrapped
