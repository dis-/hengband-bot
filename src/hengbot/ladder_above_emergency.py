"""The above-emergency layer of the dungeon ladder (dungeon_ladder.LADDER, layer "above-emergency").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the floor plans
(plan-above-survival), above the emergency ladder (ladder_emergency).  First the Recall read on
a 50F+ floor without the *Destruction* means (owner 2026-11-14, destruction_use).  (The
committed STRONG-tier hunt stood here until the owner's 2026-11-15 Q8 「緊急の逃げの後に回す」: it
is the summoner-shots layer's first rung now.)  ``PASS`` hands the decision on to the layers
below.  scripts/dungeon_ladder_lint.py reads the rows here
(dungeon_ladder.LAYER_MODULES), so the table still states this order.
"""
from __future__ import annotations

from hengbot import deep_climb, destruction_use
from hengbot.dungeon_ladder import PASS


def key(policy, snapshot):
    """The above-emergency layer's answer, or PASS when none of its rungs acts."""
    # Owner 2026-11-22 (the net under 「破壊を持っていないのに50F以降にいるのが不具合」): a 50F+
    # floor entered by a descent without the means is a named stop (deep_climb).
    stop = deep_climb.stop_key(policy, snapshot)
    if stop is not None:
        return stop
    # Owner 2026-11-14 「50F以降で破壊手段なしの探索は許可しない。敵への対処以前に手段が尽きた
    # 時点で帰還させる。」 (destruction_use.means_spent_recall_key).
    means_spent = destruction_use.means_spent_recall_key(policy, snapshot)
    if means_spent is not None:
        return means_spent
    return PASS
