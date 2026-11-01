"""D54 (Q1): n1-b life-284: a device waiting for Identify is shelved, not carried.

Recorded stop (2026-11-01 00:55:32, turn 610826, build bot-f9c921d32, three
restarts escalated to a new character): 19 items in the pack (4 free, the
terminal reserve).  Four unknown devices (a rod, a wand, two staves) waited
for Identify, the Identify staves held 12 of the 20 charges a 10F+ departure
needs, and only the two kept diggers were depositable.  The Alchemist's
Identify scroll and the Magic shop's staves each needed a fifth free slot
(shop_selector.pack_refusal "full-pack-nonstacking"), so the Alchemist stop
was skipped on its shelf evidence and the identification need held the
town's need registry: departure_block.failed ["identify_staff_ready",
"home_candidate_resolved", "identification_need_clear",
"departure_identification_need_clear"].  f097b327f shelves only equipment.

Owner 2026-11-01: 「魔法道具も自宅に預ける」 -- extend 10-31 「鑑定待ちの装備は
自宅に預け極力持ち歩かない」 to devices: shelve unknown rods, wands and staves
waiting for identification at Home to free the slot, buy the identification
means, then withdraw and identify them.

The visit is replayed from the town arrival board: every recorded ring row
goes through the production response consumer and the public chooser decides
on the recorded decision boards (tests/test_idstaff_stockout_kit_recorded.py's
replay).  The live keys hold through the Alchemist; on the next board the
recorded process walked to the Temple.  From there the replies are
constructed (tests/test_unid_deposit_recorded.py's harness, DECLARED
CONSTRUCTED) and every key goes through the production executor.  Fixture:
tests/extract_unid_device_deposit_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from pathlib import Path

from hengbot.model import parse_snapshot
import tests.test_unid_deposit_recorded as recorded
from tests.test_idstaff_stockout_kit_recorded import IdstaffStockoutKitRecordedTest


FIXTURE = Path(__file__).with_name("fixtures") / "unid-device-deposit-20261101.json.gz"
DEVICES = ("金メッキのロッド", "鉛メッキの魔法棒", "エゾマツの杖", "竹の杖")
# The recorded process's first board after the Alchemist (decision 1138).
AFTER_ALCHEMIST = 16
# The periodic save and dump follow the CLI's timers, not the board.
TIMER_BOARDS = (1, 2)
HOME_TRAVEL = "\x1b`n(."


class UnidentifiedDeviceDepositRecordedTest(recorded.UnidentifiedDepositRecordedTest):
    fixture = FIXTURE
    replay = IdstaffStockoutKitRecordedTest.replay

    def setUp(self):
        super().setUp()
        # DECLARED CONSTRUCTED: the shops this visit never entered answer with
        # their last pages of the character's earlier visits (rotated ring).
        for store, page in self.case["previous_pages"].items():
            self.pages[int(store)] = copy.deepcopy(page)

    def test_recorded_stop(self):
        decision = self.case["decision"]
        self.assertEqual((decision["turn"], decision["reason"]),
                         (610826, "town:blocked:departure-unsatisfiable"))
        self.assertEqual(decision["departure_block"]["failed"],
                         ["identify_staff_ready", "home_candidate_resolved",
                          "identification_need_clear", "departure_identification_need_clear"])
        self.assertEqual(decision["shop_selector"]["pack_refusal"], "full-pack-nonstacking")
        self.assertEqual(decision["inventory"], {"used": 19, "free": 4})
        board = parse_snapshot(copy.deepcopy(self.case["board"]))
        self.assertEqual([item.name for item in board.inventory if not item.known], list(DEVICES))
        recorded_keys = [(row["key"], row["reason"]) for row in self.case["decisions"]]
        self.assertEqual(recorded_keys[AFTER_ALCHEMIST], ("\x1b`n$.", "shop:travel"))

    def shelve(self):
        """Replay to the first board after the Alchemist and shelve one device."""
        policy, raw, keys = self.replay(AFTER_ALCHEMIST)
        recorded_keys = [(row["key"], row["reason"]) for row in self.case["decisions"]]
        for index in range(AFTER_ALCHEMIST):
            if index not in TIMER_BOARDS:
                self.assertEqual((str(keys[index][0]), keys[index][1]), recorded_keys[index], index)
        key, reason = str(keys[-1][0]), keys[-1][1]
        # The device deposit makes the scroll's room: Home before the Temple.
        self.assertEqual((key, reason), (HOME_TRAVEL, "shop:travel"))
        following = self.reply(raw, key)
        self.post(policy, raw, key, following)
        raw = following
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy.observe_store_screen(board.store is not None)
        key = str(policy.choose_key(board))
        self.assertEqual(policy.last_reason, "home:atomic-deposit", key)
        following = self.reply(raw, key)
        self.post(policy, raw, key, following)
        return policy, following

    def test_waiting_device_is_shelved_to_make_the_scrolls_room(self):
        policy, raw = self.shelve()
        deposited = [name for kind, name in self.events if kind == "deposit"]
        self.assertEqual(len(deposited), 1)
        self.assertIn(deposited[0], DEVICES)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(23 - len(board.inventory), 5)

    def test_shelved_device_take_back_is_filed_once_a_source_is_carried(self):
        policy, raw = self.shelve()
        shelved = next(name for kind, name in self.events if kind == "deposit")
        devices = set(DEVICES)

        def filed(reason, key):
            request = policy._home_errand.request
            return bool(request is not None and request.purpose == "identification-catalog"
                        and request.signature[0] in devices)

        # The freed slot buys the Identify scrolls; the carried devices are
        # identified, and a shelved one is filed for a Home take.
        raw, reasons = self.drive(policy, raw, limit=30, done=filed)
        request = policy._home_errand.request
        bought = [name for kind, name in self.events if kind == "buy"]
        self.assertIn("鑑定の巻物", bought)
        shelved_now = {name for kind, name in self.events if kind == "deposit"} & devices
        self.assertIn(shelved, shelved_now)
        self.assertIn(request.signature[0], shelved_now)
        self.assertTrue(policy._home_candidate_waiting)
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        self.assertIsNotNone(policy._find_identification_source(
            board, full=False, reliable_only=True, reservation_target=request.signature))

    # The inherited Identify-staff scenarios belong to the life-427 fixture.
    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None


if __name__ == "__main__":
    import unittest
    unittest.main()
