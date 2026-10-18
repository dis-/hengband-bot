"""Recorded pin: the Home-full sale keeps the standing Word of Recall target.

Live soak 2026-10-18 14:09 (issue #68), Level 27: Home was full, the relief
withdrew the Home stack of Word of Recall (``5pk\\x1b``,
``home-errand:atomic-withdraw:full-home-sale``); it merged with the carried 7
and the Alchemist bought all 10 (``d110\\ry``).  At 14:01 the requirement was
Recall 7/9 (fundraising mode ``prepare``); after the trip it was 0/10 and the
bot waited for a Temple restock (``town:wait-restock:temple``, 14:42).

The sale passed the retention gate only because fundraising (``mine`` /
``scavenge``) suspends the Recall target for its own trip
(``_recall_required_target`` returns 0); the standing target applies again
when the trip ends.

Fixture rows: the issue #67 capture B (12:38, same soak, Level 26) -- the
Home ``~9`` list, the outside approach board and the Home page board.

DECLARED CONSTRUCTED: the 14:09 boards are not captured.  The 12:38 boards
are edited to the 14:09 counts: the Home's Treasure Detection stack (5) is
replaced by a Word of Recall stack (3), on the list and on the Home page, and
the carried Recall stack is 7.  The fundraising mode is set to ``scavenge``
(the 14:09 mode is not captured; ``mine`` / ``scavenge`` is the only state in
which the carried Recall stack has no retention).  The planned depth is 20
(standing Recall target 9), as in the issue #67 pin.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _parse_items
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "sale-inscribe-buy-20261018.jsonl.gz"
RECALL_NAME = "帰還の詔の巻物"
DETECTION_NAME = "財宝感知の巻物"


def _recall_at_home(row, count):
    """Return ``row`` with the Home Treasure Detection stack made Recall."""
    row = copy.deepcopy(row)
    items = (row["knowledge"]["items"] if "knowledge" in row
             else row["store"]["items"])
    item = next(item for item in items if item["name"] == DETECTION_NAME)
    item.update(name=RECALL_NAME, sval=11, count=count)
    return row


def _carried_recall(board, count):
    board = copy.deepcopy(board)
    next(item for item in board["inventory"]
         if item["name"] == RECALL_NAME)["count"] = count
    return board


class HomeFullSaleKeepsRecallRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.home, cls.approach, cls.inside = rows[4], rows[5], rows[6]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy_on(self, home, approach, mode):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy._in_store_ops_enabled = True
        policy._equipment_optimization_last_depth = 20
        snapshot = parse_snapshot(approach, self.monrace)
        policy.prime(snapshot)
        policy._skill_exp_cache = (
            0, 0, snapshot.player.level, policy._town_visit_epoch
        )
        policy.consume_home_knowledge(tuple(_parse_items(
            home["knowledge"]["items"], protocol=home.get("protocol_version"),
        )))
        policy._fundraising_mode = mode
        return policy

    def _relief_pick(self, home, approach, inside, mode):
        """Replay the Home page board; return the picked relief stack."""
        policy = self._policy_on(home, approach, mode)
        snapshot = parse_snapshot(inside, self.monrace)
        policy.observe_store_screen(True)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        relief = policy._home_full_relief or {}
        sale = relief.get("sale")
        return (sale[0][0] if sale else None), relief.get("mode"), (
            str(key), policy.last_reason)

    def _boards(self, carried=7, home_recall=3):
        return (_recall_at_home(self.home, home_recall),
                _carried_recall(self.approach, carried),
                _carried_recall(_recall_at_home(self.inside, home_recall), carried))

    def test_recall_below_standing_target_is_not_sold_while_scavenging(self):
        # 99c2fa87 picked the Recall stack here (the live 14:09 sale).
        self.assertEqual(
            self._relief_pick(*self._boards(), "scavenge"),
            ("厚布よろい [5,+0]", "sale",
             ("\x1b", "home:full-queue-surplus-withdraw")),
        )

    def test_recall_below_standing_target_is_not_disposed_by_either_selector(self):
        home, approach, inside = self._boards()
        for mode in ("scavenge", "mine"):
            with self.subTest(mode=mode):
                policy = self._policy_on(home, approach, mode)
                snapshot = parse_snapshot(inside, self.monrace)
                stack = next(item for item in policy._home_knowledge_items
                             if item.is_recall_scroll)
                self.assertEqual(stack.count, 3)
                # 99c2fa87: a sale candidate and a destroy candidate.
                self.assertIsNone(policy._home_full_sale_candidate(snapshot, stack))
                self.assertIsNone(policy._home_full_discard_candidate(snapshot, stack))

    def test_control_recall_outside_fundraising_is_unchanged(self):
        # The ordinary retention already keeps the carried Recall.
        self.assertEqual(
            self._relief_pick(*self._boards(), None)[0], "厚布よろい [5,+0]")

    def test_control_recall_above_standing_target_is_still_sold(self):
        # A second Home Recall stack (inscribed, so it does not merge) keeps
        # 9 = the standing target after the 3 are sold with the carried 7.
        home, approach, inside = self._boards()
        home = copy.deepcopy(home)
        spare = next(item for item in home["knowledge"]["items"]
                     if item["name"] == "サモン・モンスターの巻物")
        spare.update(name=RECALL_NAME + " {@r1}", inscription="@r1", sval=11,
                     count=9, fully_known=True, is_broken=False)
        policy = self._policy_on(home, approach, "scavenge")
        snapshot = parse_snapshot(inside, self.monrace)
        stacks = sorted((item for item in policy._home_knowledge_items
                         if item.is_recall_scroll), key=lambda item: item.count)
        self.assertEqual([item.count for item in stacks], [3, 9])
        self.assertIsNotNone(policy._home_full_sale_candidate(snapshot, stacks[0]))
        # Selling the 9 (plus the carried 7) would leave 3 < 9.
        self.assertIsNone(policy._home_full_sale_candidate(snapshot, stacks[1]))
        self.assertEqual(
            self._relief_pick(home, approach, inside, "scavenge")[0], RECALL_NAME)


if __name__ == "__main__":
    unittest.main()
