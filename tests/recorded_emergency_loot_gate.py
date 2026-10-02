"""Keep recorded replays on the emergency-return loot gate of their recorded era.

One declared wall; production code and the loot-gate pins remain untouched.

USER DECISION 2026-10-02 19:0x 「帰還が進んでいる間だけ止める」 (6c0910fb)
narrowed the gate: ``_emergency_return_active`` now shuts normal loot out only
while the return progresses (``_emergency_return_progressing``).  The captures
replayed by tests whose subject is NOT loot suppression were recorded (or last
pinned) when the flag alone closed the gate; on their recorded boards the new
gate seeks loot the recorded process never sought, so every later board would
be the effect of a key the live bot did not send (R4).
``pre_progressing_loot_gate_rule`` / ``pre_progressing_loot_gate_replay``
restore the recorded-era gate (progressing == the flag) for such replays.
Replays whose subject IS the loot gate pin the decided rule instead
(tests/test_loot_suppression_returning_recorded.py,
tests/test_policy_identification.py, tests/test_ownership_s2b1b_close_pairs.py).
"""

from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch

from hengbot.policy import HengbotPolicy


def _recorded_era_gate(policy, _snapshot):
    """Before 6c0910fb the flag alone closed the normal-loot gate."""
    return policy._emergency_return_active


@contextmanager
def pre_progressing_loot_gate_rule():
    """Close the loot gate on the flag alone (see the module text)."""
    with patch.object(
        HengbotPolicy, "_emergency_return_progressing", _recorded_era_gate
    ):
        yield


def pre_progressing_loot_gate_replay(replay):
    """Run ``replay`` under ``pre_progressing_loot_gate_rule``."""
    @wraps(replay)
    def wrapped(*args, **kwargs):
        with pre_progressing_loot_gate_rule():
            return replay(*args, **kwargs)

    return wrapped
