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
