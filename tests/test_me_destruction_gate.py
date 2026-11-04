"""Owner 2026-10-31 21:30: which absorbed powers count for which requirement.

「*破壊*の杖のみ、成功率が80%以上なら取り込んだ魔力を要求に数える。帰還テレポート
回復は信頼度が違うので薬巻物も要求する。」

Board: the recorded n1-c life-065 Outpost board (Lv27 Magic-Eater, turn
4833381; tests/fixtures/me-light-waiver-life065-20261031.json.gz).  DECLARED
CONSTRUCTED: the absorbed-power lists the game displays (``_magic_eater_power_list``
rows with the counts and failure percents named per case), observed by one
public ``choose_key``.  The 50F+ gate is read through the policy's own
predicates and its viewer report (``procurement_requirements``) with the
intended arrival depth patched to 50F (production clamps it below 50 while
``destruction_use.holds_means`` is False: no 50F+ dive is allowed yet, so
the gate count only matters once the use logic exists).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from hengbot import me_capability
from hengbot.model import SV_STAFF_DESTRUCTION, TVAL_STAFF
from hengbot.model import parse_snapshot
from tests import test_q2_tower_recharge_recorded as q2_town

LIFE065 = Path(__file__).with_name("fixtures") / "me-light-waiver-life065-20261031.json.gz"


def power_list(kind, rows):
    """DECLARED CONSTRUCTED: one displayed list: (name, current, max, fail%)."""
    return {"kind": kind, "rows": [
        {"name": name, "current": current, "max": count, "fail": fail, "success": 100 - fail}
        for name, current, count, fail in rows]}


class AbsorbedRequirementTest(unittest.TestCase):
    _town = q2_town.Q2TowerRechargeRecordedTest
    policy = _town.policy

    @classmethod
    def setUpClass(cls):
        cls._town.setUpClass.__func__(cls)
        with gzip.open(LIFE065, "rt", encoding="utf-8") as stream:
            cls.board_raw = json.load(stream)["boards"]["27"]

    def observed(self, *lists, class_id=16):
        """A policy that saw each list (one public decision per list)."""
        raw = copy.deepcopy(self.board_raw)
        raw["player"]["class_id"] = class_id
        policy = self.policy(raw)
        for listed in lists:
            shown = dict(copy.deepcopy(raw), _magic_eater_power_list=listed)
            policy.choose_key(parse_snapshot(shown, self.monraces))
        return policy, parse_snapshot(copy.deepcopy(raw), self.monraces)

    def gate(self, policy, board):
        with patch.object(policy, "_intended_dive_depth", return_value=50):
            report = {row["item"]: row for row in policy.procurement_requirements(board)}
            return policy._missing_destruction_uses(board), report.get("*Destruction* uses")

    def test_destruction_counts_only_at_eighty_percent_success(self):
        for fail, counted in ((20, 6), (15, 6), (21, 0)):
            with self.subTest(fail=fail):
                policy, board = self.observed(power_list("staff", [("*破壊*", 6, 9, fail)]))
                self.assertEqual(me_capability.replacing_charges(
                    policy, board, (TVAL_STAFF, SV_STAFF_DESTRUCTION)), counted)
                self.assertEqual(policy._total_destruction_uses(board), counted)
                self.assertEqual(policy._has_destruction_method(board), counted > 0)
                missing, row = self.gate(policy, board)
                # 50F asks five uses; six absorbed charges at 80%+ meet it.
                self.assertEqual(missing, 0 if counted else 5)
                self.assertEqual(row is None, bool(counted), row)

    def test_destruction_without_a_displayed_rate_or_class_counts_nothing(self):
        policy, board = self.observed()
        self.assertEqual(policy._total_destruction_uses(board), 0)
        policy, board = self.observed(power_list("staff", [("*破壊*", 6, 9, 10)]), class_id=0)
        self.assertEqual(policy._total_destruction_uses(board), 0)

    def test_recall_teleport_and_healing_still_need_scrolls_and_potions(self):
        plain_policy, plain = self.observed()
        before = plain_policy._supply_ledger(plain, plain_policy._planned_depth())
        policy, board = self.observed(
            power_list("staff", [("テレポート", 9, 9, 5), ("治癒", 9, 9, 5)]),
            power_list("rod", [("帰還", 0, 2, 5), ("体力回復", 0, 2, 5)]))
        after = policy._supply_ledger(board, policy._planned_depth())
        for kind in ("recall", "teleport", "cure"):
            with self.subTest(kind=kind):
                self.assertEqual(after[kind].count, before[kind].count)
                self.assertEqual(after[kind].required_departure, before[kind].required_departure)
        self.assertEqual(after["recall"].count, policy._count_recall_scrolls(board))
        self.assertEqual(after["teleport"].count, policy._count_teleport_scrolls(board))
        self.assertEqual(after["cure"].count, policy._count_cure_critical_potions(board))


if __name__ == "__main__":
    unittest.main()
