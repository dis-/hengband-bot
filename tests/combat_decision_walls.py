"""Declared walls: recorded combat choices before the 2026-10-03 decisions.

USER DECISION 1 (verbatim): 「次に受けるダメージ予測で判断する。基本的には
回復を優先するが、回復量を上回るならテレポートを優先する。回復しても状況が
悪化するだけだからである。」 Clarification: 「1ターン分の95%値 (Recommended)」,
「見える敵の1ターン分の運用値（95%）と、直近1手の実被害の大きい方を使う。」

The Identify-staff-swap capture predates this decision.  At replay index 1785
(turn 6068939), HP 384/731 is below 431, next-turn damage 146 is below the
Healing potion's 300, so the new emergency ladder heals ('qc') instead of
the recorded teleport ('rf').  These pins concern the later town staff swap.
Disable the new heal-first helper.  The later landing decision also matters:
USER DECISION 2026-10-03 11:4x: 「テレポートで逃げた攻撃では後退しない」.
Commit b1e0e349 forgets the pre-teleport unseen hit on landing 1786, so the
bot rests instead of the recorded retreat attempt that the low-HP walk gate
replaces with a heal.  Forget the posted-read watch, as the recorded-era
policy did, to retain that pending hit.  Ordinary healing stays active.
USER DECISION 4 (verbatim): 「強敵との戦闘開始時に飲む」, 「予測被害が HP の
一定割合を超える戦闘に入った時点で飲む。消費は増えるが被害は減る。」,
「HP の5割 (Recommended)」; 「逃走時の判定はそのまま」.  At index 1795 the
new strong-fight filter quaffs Speed ('qa') instead of the recorded melee
('9').  Bypass that filter, preserving the older escape-Speed rule.
USER DECISION 5: 「1回で最大HPの1割以上削られた時か、HPが低HPの閾値
（最大HP×50%と最大HP−300の大きい方）未満の時だけ」; two unexplained
losses: 「合計で最大HPの1割以上か低HP閾値未満」.
The unseen-scratch bound also changes index 2766: the replay retreats
('4', unseen:reverse-choke) instead of the recorded teleport ('rf').  Use
the shared pre_unseen_scratch_bound_rule (tests/unseen_scratch_walls.py),
which documents and quotes the single-hit and two-hit decisions.
No recorded key, board or expected value is replaced by these walls.
"""
from contextlib import contextmanager
from unittest.mock import patch

from hengbot.policy import HengbotPolicy
from unseen_scratch_walls import pre_unseen_scratch_bound_rule


@contextmanager
def pre_combat_decisions_rule():
    """Keep recorded healing, landing memory and fighting-action priority."""
    original = HengbotPolicy.confirm_key_posted

    def recorded_post(policy, key):
        result = original(policy, key)
        policy._teleport_read_watch = None
        return result

    with patch.object(
        HengbotPolicy, "_low_hp_heal_first_potion", return_value=None
    ), patch.object(
        HengbotPolicy, "_strong_fight_speed_filter",
        lambda policy, snapshot, key: key,
    ), patch.object(
        HengbotPolicy, "confirm_key_posted", recorded_post
    ), pre_unseen_scratch_bound_rule():
        yield
