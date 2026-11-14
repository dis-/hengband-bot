"""This visit's purchases go to Home when nothing else sheds the weight (n1-c life-208).

n1-c life-208 (Magic-Eater Lv8, build e897edf2d) bought its quest supplies at the
Outpost on 2026-11-14 23:11 (20 throwing torches, the Rod of Pesticide, a Wand of
Disarming, Heroism), threw two torches at a town mob, picked one up and bought one
more, shelved an empty bottle and a scroll at Home, and stood at 1409 over a 1400
limit with every carried item retained (the weight relief's ``retained-only``:
supply ledger, quest carry, heroism, this visit's purchases).  Nothing was left to
sell (the inventory_weight_ready leaf's overweight-sale rescue answered None) and
the visit stopped under town:blocked:survival:inventory_weight_ready.

Owner 2026-11-15 「今回買った品を要る分だけ預ける」: the leaf's next rescue
(departure_rescues ``purchase-deposit``) releases the fewest of this visit's
purchases whose weight clears the excess -- here one Wand of Disarming (1.0 lb for
a 0.9 lb excess, lighter than the 1.5 lb rod) -- and takes Home's route; the weight
relief deposits it at Home and the visit departs.

Recorded: the incident capture's town-arrival checkpoint and its whole journal
(tests/extract_n1c_208_weight_purchase_1115_fixture.py), rows 0-89 decided through
the public choose_key and compared with the record.

DECLARED CONSTRUCTED: the boards after the stop board, and the stop board with
a heavier staff (the third test).  Home's page is row 87's
recorded entry (the response lines of the Home page the recorded bot deposited on)
with the stop board's pack; the outside boards are the stop board, its turn
advanced, and after the deposit without the wand.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-208-weight-purchase-1115"
STOP_ROW = 90
STOP = "town:blocked:survival:inventory_weight_ready"
HOME_PAGE_ROW = 87
WAND = ("トラップ解除の魔法棒 (9回分)", 65, 4)
WAND_SLOT = "h"


class N1c208WeightPurchase1115RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.replayed = []
        for recorded, supply in steps[:STOP_ROW]:
            key = policy.choose_key(supply())
            cls.replayed.append((recorded["row"], (key, policy.last_reason),
                                 (recorded["key"], recorded["reason"])))
            policy.confirm_key_posted(recorded["key"])
        cls.board = steps[STOP_ROW][1]()
        cls.checkpoint = checkpoint_bytes(policy)
        cls.ledger = Path(cls.scratch.name) / "knowledge.jsonl"

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, decided, recorded in self.replayed:
            self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        self.addCleanup(lambda: self.policy._home_disposal.history_path.unlink(missing_ok=True))

    def line(self):
        return json.loads(self.journal[STOP_ROW]["line"])

    def board_of(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge)

    def enter_home(self, turn):
        """DECLARED CONSTRUCTED: row 87's Home entry with the stop board's pack."""
        line = self.line()
        records = []
        for text in self.journal[HOME_PAGE_ROW]["inputs"]:
            record = json.loads(text)
            for field in ("inventory", "equipment", "player"):
                if field in record:
                    record[field] = copy.deepcopy(line[field])
            record["turn"] = turn
            records.append(record)
        _consume_response_sequence(
            [json.dumps(record, ensure_ascii=False) + "\n" for record in records],
            self.policy, lambda _key: True, self.policy._monrace_knowledge,
            parse_snapshots=False, knowledge_ledger_path=self.ledger)
        self.policy.observe_store_screen(True)
        self.assertEqual(records[-1]["store"]["store_type"], 7)
        return records[-1]

    def decide(self, raw):
        key = self.policy.choose_key(self.board_of(raw))
        self.policy.confirm_key_posted(key)
        return key, self.policy.last_reason

    def test_the_stop_board_releases_the_lightest_purchase_and_walks_home(self):
        self.assertEqual(self.journal[STOP_ROW]["reason"], STOP)
        policy, board = self.policy, self.board
        self.assertEqual((policy._inventory_weight(board), policy._inventory_weight_limit(board)),
                         (1409, 1400))
        relief = policy._weight_relief_selection(board)
        self.assertEqual(relief.route, "retained-only")
        held = {slot: reason for slot, _, _, reason in relief.retained}
        self.assertEqual((held["g"], held[WAND_SLOT]), ("visit-purchase", "visit-purchase"))
        self.assertIsNone(policy._overweight_surplus_sale_key(board))

        key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), ("4", "shop:approach"))
        self.assertIsNone(policy._town_blocked_reason)
        self.assertEqual(policy._departure_rescue_last, ("inventory_weight_ready", "purchase-deposit"))
        self.assertEqual(policy._overweight_purchase_release[1], ((WAND, 1),))
        relief = policy._weight_relief_selection(board)
        self.assertEqual((relief.route, [item.slot for item in relief.deposits]),
                         ("deposit", [WAND_SLOT]))

    def test_home_takes_the_wand_and_the_visit_departs(self):
        policy = self.policy
        key = policy.choose_key(self.board)
        policy.confirm_key_posted(key)
        line = self.line()
        # The first entry closes the Home knowledge scan the stop board offered.
        page = self.enter_home(line["turn"] + 10)
        self.assertEqual(self.decide(page), ("\x1b", "home:scan-complete-from-open-page"))
        self.decide(page)
        self.decide(page)
        policy.observe_store_screen(False)
        outside = copy.deepcopy(line)
        outside["turn"] += 20
        self.assertEqual(self.decide(outside), ("4", "shop:approach"))
        page = self.enter_home(line["turn"] + 30)

        self.assertEqual(self.decide(page), (f"d{WAND_SLOT}\x1b", "home:weight-overload-deposit"))

        policy.observe_store_screen(False)
        outside = copy.deepcopy(line)
        outside["inventory"] = [item for item in outside["inventory"] if item["slot"] != WAND_SLOT]
        outside["turn"] += 40
        self.assertFalse(policy._inventory_overweight(self.board_of(outside)))
        reasons = [self.decide(outside)[1] for _ in range(3)]
        self.assertIn("town:recall-to-yeek-cave", reasons)
        self.assertIsNone(policy._town_blocked_reason)

    def test_purchases_that_cannot_clear_the_excess_keep_the_stop(self):
        policy = self.policy
        # DECLARED CONSTRUCTED: the stop board with the retained mana-food staff
        # 9.0 lb heavier, an excess (9.9 lb) the rod and the wand (2.5 lb) cannot clear.
        raw = self.line()
        staff = next(item for item in raw["inventory"] if item["slot"] == "j")
        staff["weight"] += 90
        board = self.board_of(raw)
        relief = policy._weight_relief_selection(board)
        self.assertEqual((relief.route, relief.excess), ("retained-only", 99))

        key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), ("5", STOP))
        self.assertIsNone(getattr(policy, "_overweight_purchase_release", None))


if __name__ == "__main__":
    unittest.main()
