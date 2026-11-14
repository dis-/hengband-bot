"""n1-c life-210's 04:58 town stop: scavenge on the General shelf the town plan trusts.

n1-c life-210 (Lv8 zombie Magic-Eater after Q34 and Q1) stopped at 2026-11-15 04:58 on
town:blocked:survival:recall_departure_ready (turn 105333, 282 gold, Word of Recall 1 of 9).  No
digger could be had (the General store's cheapest, シャベル, 1,186 gold) and the pack held 11
Treasure Detection, so the owner's 10-23 poverty exception (scavenge 1F with the carried
detection, policy_fundraising ``_diggerless_scavenge_allowed``) applied, but it read only a
General page observed on this visit.  The need registry skipped the General stop on the previous
visit's page (turn 100978, within its restock window: ``_shelf_evidence_skips_need``), so no page
of this visit ever came, the set stayed in ``prepare`` (whose departure asks the ordinary recall
target) and the visit stopped.  The exception now reads the same remembered page the registry
trusts (``_general_shelf_evidence_page``): at row 6 the set is a scavenge and the visit walks to
the dungeon entrance.

Recorded: the capture's town-arrival checkpoint and journal rows 0-7
(tests/extract_n1c_210_scavenge_shelf_1115_fixture.py), replayed through the public ``choose_key``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import STORE_GENERAL
from support.town_arrival_fixture import load

FIXTURES = Path(__file__).with_name("fixtures")
SCAVENGE = FIXTURES / "n1c-210-scavenge-shelf-1115"


class _Replay(unittest.TestCase):
    def replay(self, fixture, upto):
        """(policy, the board of row ``upto``, its key) after rows 0..upto-1 decided as recorded."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, _journal, rows = load(fixture, Path(scratch.name))
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        for recorded, supply in rows[:upto]:
            board = supply()
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            policy.confirm_key_posted(key)
        board = rows[upto][1]()
        return policy, board, policy.choose_key(board), rows[upto][0]


class ScavengeOnTheRememberedGeneralShelfTest(_Replay):
    def test_the_visit_scavenges_instead_of_waiting_in_prepare(self):
        policy, board, key, recorded = self.replay(SCAVENGE, 6)
        self.assertEqual(recorded["reason"], "shop:travel")  # the live visit went on in prepare
        self.assertIsNone(policy._current_town_supplier_page(board, STORE_GENERAL))
        page = policy._general_shelf_evidence_page(board)
        self.assertIsNotNone(page)
        self.assertTrue(any(item.is_digging_tool for item in page.items))
        self.assertTrue(all(item.price > board.player.gold
                            for item in page.items if item.is_digging_tool))
        self.assertTrue(policy._diggerless_scavenge_allowed(board))
        self.assertEqual(policy._fundraising_mode, "scavenge")
        self.assertEqual(policy._recall_required_target(board), 0)
        self.assertEqual((policy.last_reason, key), ("town:travel-entrance", "\x1b`n>."))

    def test_without_the_remembered_page_the_exception_does_not_apply(self):
        policy, board, _key, _recorded = self.replay(SCAVENGE, 6)
        policy._in_store_attribute("_shelf_evidence").get("pages", {}).clear()
        self.assertIsNone(policy._general_shelf_evidence_page(board))
        self.assertFalse(policy._diggerless_scavenge_allowed(board))


if __name__ == "__main__":
    unittest.main()
