"""Keep recorded replays on the junk scope of their recorded boards.

``pre_junk_scope_rule`` / ``pre_junk_scope_replay``: replays whose subject is
not junk disposal and that were recorded (or last pinned) before the owner
decisions of 2026-10-20 (「広げる（設計してから）」: cursed items, harmful
consumables, spellbooks a warrior cannot read and ammunition for an unused
launcher are junk too; Q6 「壊す」: cursed egos as well) answer the one junk
predicate ``_junk_class`` as before step 1a: only remains (tval 1/3/10) and
emptied chests are junk, never a bounty or an artifact.  Without it the
recorded Homes' つよしスペシャルの薬, unused arrows, an unreadable book or a
broken 暗闇の真鍮のランタン are destroyed before the sale, withdrawal or
overflow choice these replays pin.  The third/fourth-book keep rule stays: a
book is never a remain, so it cannot fire under this wall.  Tests whose
subject is junk disposal pin the new behaviour instead
(tests/test_junk_scope_recorded.py).
"""

from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch

from hengbot.policy import HengbotPolicy


def pre_junk_scope_class(policy, _snapshot, item):
    """The junk predicate of #70 (2026-10-18), before the 2026-10-20 widening."""
    if item.is_bounty or item.is_artifact:
        return None
    if item.tval in {1, 3, 10} or (
            item.is_chest and policy._is_disposable_item(item)):
        return "remains"
    return None


@contextmanager
def pre_junk_scope_rule():
    """Answer ``_junk_class`` by the pre-2026-10-20 junk scope."""
    with patch.object(HengbotPolicy, "_junk_class", pre_junk_scope_class):
        yield


def pre_junk_scope_replay(replay):
    """Run ``replay`` under ``pre_junk_scope_rule``."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_junk_scope_rule():
            return replay(*args, **kwargs)

    return wrapped


# The town junk-destroy-first step of ``HengbotPolicy._decide`` is the only
# caller of the town producer entry under this rung name (the before-return
# disposal calls ``_worthless_junk_destroy_key`` directly).
TOWN_JUNK_STEP_RUNG = "_worthless_junk_destroy_key"


@contextmanager
def pre_town_junk_step_rule():
    """Disable only the town junk-destroy-first step (#95 step 1b).

    For recorded replays whose subject is not junk disposal.  The owner
    decisions 2026-10-18 (#70: remains are never carried home, disposed before
    the return) and 2026-10-20 (#95: junk is destroyed in town and never
    deposited) make the town step destroy carried remains / junk under weight
    or pack-slot pressure, ahead of the recorded decision these replays pin.
    Tests whose subject is junk disposal pin the new behaviour instead
    (tests/test_junk_town_weight_recorded.py).  Composable with
    ``pre_junk_scope_rule`` (it patches a different seam).
    """
    entry = HengbotPolicy._town_producer_entry

    def without_town_junk_step(self, rung_name, call, *args, **kwargs):
        if rung_name == TOWN_JUNK_STEP_RUNG:
            return None
        return entry(self, rung_name, call, *args, **kwargs)

    with patch.object(HengbotPolicy, "_town_producer_entry", without_town_junk_step):
        yield


def pre_town_junk_step_replay(replay):
    """Run ``replay`` under ``pre_town_junk_step_rule``."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_town_junk_step_rule():
            return replay(*args, **kwargs)

    return wrapped


@contextmanager
def pre_home_junk_sweep_rule():
    """Disable only the one-time Home junk sweep (#95 step 1b-2, 2026-10-22).

    For recorded replays whose capture predates the sweep.  The sweep starts
    on a Home page where the Home page owner found no Home work and leaves
    the Home (reason ``home:junk-sweep-withdraw``) ahead of the recorded exit
    these replays pin.  Its only entry is ``_begin_home_junk_sweep``; a
    disabled entry never files a sweep relief, so every later decision runs
    as before the sweep.  Tests whose subject is the sweep pin the new
    behaviour instead (tests/test_junk_home_sweep_recorded.py).  Composable
    with the other walls of this module (it patches a different seam).
    """
    def without_home_junk_sweep(self, snapshot):
        return False

    with patch.object(HengbotPolicy, "_begin_home_junk_sweep", without_home_junk_sweep):
        yield


def pre_home_junk_sweep_replay(replay):
    """Run ``replay`` under ``pre_home_junk_sweep_rule``."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_home_junk_sweep_rule():
            return replay(*args, **kwargs)

    return wrapped
