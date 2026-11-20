"""The 99F/100F Teleportation errand in every town the Black Market tour or the circuit visits.

Owner 2026-11-20 「4つの街を回ってテレポートの巻物を買い足す処理をつけて」 (finale_teleport_tour).
n1-c life-217's visit of 2026-11-21 02:57-03:01 (26 of the 40 Teleportation, none at Home) went
round the other towns on the Black Market tour (town:cross-town-bm-tour:travel-1/2/3) and read the
recall in town 3 with the 26: the Alchemist/General errand (angband_finale.CATEGORY) was a town need
but no NeedSpec of the registry, so it was never a live claim, no town's plan stopped there, and
the circuit, which waits for this town's suppliers, was never due.

Recorded: that visit's town-arrival checkpoint (Zul, turn 7002152) and two of its recorded town
boards (tests/extract_finale_tour_after_bm_1121_fixture.py): town 3 at turn 7019700, where the
recall was read, and town 1 at turn 6996376, its Alchemist shelf seen without the scrolls at turn
6995315 (the previous loop of the circuit).

DECLARED CONSTRUCTED: the boards decided by the arrival's policy (no decision of the visit
replayed); the suppliers marked visited where a test says so.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, finale_teleport_tour
from hengbot.model import STORE_ALCHEMIST, STORE_GENERAL, parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-finale-tour-after-bm-1121"


class FinaleTourAfterBmRecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, _steps = load(FIXTURE, Path(self.scratch.name))
        recorded = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))
        self.boards = {name: parse_snapshot(raw, self.policy._monrace_knowledge)
                       for name, raw in recorded.items()}

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def test_the_last_bm_town_stops_at_its_alchemist(self):
        policy, board = self.policy, self.boards["last-bm-town"]
        self.assertEqual(policy._effective_town_id(board), 3)
        self.assertEqual(angband_finale.carried(board, angband_finale.TELEPORT), 26)
        self.assertEqual(finale_teleport_tour.shortage(policy, board), 14)
        self.assertEqual(policy._angband_finale_errand_store(board), STORE_ALCHEMIST)
        policy._town_claims_active(board)
        self.assertIn(angband_finale.CATEGORY, policy._town_claim_categories)
        plan = policy._build_town_errand_plan(board, list(policy._decision_claim_needs[2]))
        self.assertIn(STORE_ALCHEMIST, plan.stops)
        # Not before the town's suppliers: the read there starts no circuit yet.
        self.assertFalse(finale_teleport_tour.due(policy, board))
        # Its suppliers tried (DECLARED), the read starts the circuit over the other towns.
        for store in (STORE_ALCHEMIST, STORE_GENERAL):
            policy._town_store_attempted[store] = board.turn
        self.assertTrue(finale_teleport_tour.due(policy, board))
        self.assertTrue(finale_teleport_tour.start(policy, board))
        self.assertEqual(finale_teleport_tour.circuit(policy).tried_towns, [3])

    def test_a_shelf_seen_without_them_passes_to_the_general_store(self):
        policy, board = self.policy, self.boards["alchemist-seen"]
        self.assertEqual(policy._effective_town_id(board), 1)
        self.assertTrue(policy._shelf_evidence_skips_need(board, STORE_ALCHEMIST, angband_finale.CATEGORY))
        self.assertEqual(policy._angband_finale_errand_store(board), STORE_GENERAL)
        policy._town_claims_active(board)
        plan = policy._build_town_errand_plan(board, list(policy._decision_claim_needs[2]))
        self.assertIn(STORE_GENERAL, plan.stops)

    def test_due_once_the_general_store_is_tried(self):
        policy, board = self.policy, self.boards["alchemist-seen"]
        self.assertFalse(finale_teleport_tour.due(policy, board))
        policy._town_store_attempted[STORE_GENERAL] = board.turn
        # The Alchemist never entered: its shelf was seen without them since the restock.
        self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)
        self.assertTrue(finale_teleport_tour.due(policy, board))


if __name__ == "__main__":
    unittest.main()
