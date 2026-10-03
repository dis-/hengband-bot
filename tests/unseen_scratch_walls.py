"""Declared wall: recorded boards under the pre-2026-10-03 unseen-hit rule.

USER DECISIONS 2026-10-03: with no hostile in view, an unseen spell hit reads
the emergency teleport only 「1回で最大HPの1割以上削られた時か、HPが低HPの
閾値（最大HP×50%と最大HP−300の大きい方）未満の時だけ」 (ee96afbd), and two
unexplained losses in a row only 「合計で最大HPの1割以上か低HP閾値未満」
(cd1e8611).  Both go through HengbotPolicy._unseen_loss_is_material.

Recordings made before those decisions read the teleport on any unseen spell
hit and on any two-loss streak.  The reverse-choke-loot-loop capture
(2026-10-03 11:11, Forest 32F) does so at decision 4638: HP 730/731 after a
1-HP 「何かが混乱のブレスを吐いた。」.  Every later recorded board -- the
landing, the retreat walk, the dead end -- follows that teleport, and those
pins' subjects are the retreat and the landing watch, not the read.  So the
replay runs under the recorded-era rule: every unseen loss is material.  The
new choice on the unwalled board is pinned in
tests/test_reverse_choke_loot_loop_recorded.py::UnseenScratchDivergenceTest.
"""
from contextlib import contextmanager
from unittest.mock import patch

from hengbot.policy import HengbotPolicy


@contextmanager
def pre_unseen_scratch_bound_rule():
    """Run with every unseen loss material, as before the 2026-10-03 bound."""
    with patch.object(
        HengbotPolicy, "_unseen_loss_is_material", lambda self, player, loss: True
    ):
        yield
