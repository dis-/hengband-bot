"""n1-b life-282: an Identify scroll the pack cannot hold is no identification source.

Recorded stop (2026-10-31 23:23:19, turn 345239, build bot-404e73286, three
restarts escalated to a new character): 19 items in the pack (4 free, the
terminal reserve), an 18-charge Identify staff, and three carried equipment
items (an unaware ring, an {excellent} armour, a {special} sabre) plus wands
waiting for Identify.  The observed Alchemist shelf sold Identify scrolls
within gold, so _identification_waiting_deposit kept the equipment carried
("available"), yet the pack budget refused the scroll for a fifth free slot
(shop_selector.pack_refusal "full-pack-nonstacking") and the pack-room pass
waits for carried identification work.  departure_block.failed was
["identify_staff_ready", "home_candidate_resolved",
"identification_need_clear", "departure_identification_need_clear"].

Owner 2026-10-31: 「鑑定待ちの装備は預ける　極力持ち歩かない」 -- the deposit
makes the room for the purchase.

Harness, declarations and engine replies: tests/test_unid_deposit_recorded.py
(DECLARED RECONSTRUCTED boundary, DECLARED CONSTRUCTED replies).  Fixture:
tests/extract_unid_scroll_room_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from pathlib import Path

from hengbot.model import STORE_ALCHEMIST, parse_snapshot
import tests.test_unid_deposit_recorded as recorded


WAITING = ("赤めのうの指輪", "硬革よろい [6] {高級品}", "サーベル (1d7) {特別製}")


class UnidentifiedScrollRoomRecordedTest(recorded.UnidentifiedDepositRecordedTest):
    fixture = Path(__file__).with_name("fixtures") / "unid-scroll-room-20261031.json.gz"

    def test_recorded_stop(self):
        decision = self.case["decision"]
        self.assertEqual((decision["turn"], decision["reason"]),
                         (345239, "town:blocked:departure-unsatisfiable"))
        self.assertEqual(decision["departure_block"]["failed"],
                         ["identify_staff_ready", "home_candidate_resolved",
                          "identification_need_clear", "departure_identification_need_clear"])
        self.assertEqual(decision["shop_selector"]["pack_refusal"], "full-pack-nonstacking")
        self.assertEqual(decision["inventory"], {"used": 19, "free": 4})
        policy, raw = self.boundary()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        waiting = [item.name for item in board.inventory
                   if item.is_equipment and policy._identification_flow_candidate(item)]
        self.assertEqual(waiting, list(WAITING))
        # The visit's Alchemist page sells the scroll within gold; only the
        # pack budget refuses it.
        alchemist = next(row["store"] for row in reversed(self.case["observations"])
                         if row["type"] == "store" and row["store"]["store_type"] == STORE_ALCHEMIST)
        scroll = next(item for item in alchemist["items"] if item["name"] == "鑑定の巻物")
        self.assertLessEqual(scroll["price"], board.player.gold)

    def test_waiting_equipment_is_shelved_and_the_scroll_bought(self):
        policy, raw = self.boundary()
        self.drive(policy, raw, limit=60,
                   done=lambda reason, key: any(kind == "identify" for kind, _ in self.events))
        kinds = [kind for kind, _ in self.events]
        deposited = next(name for kind, name in self.events if kind == "deposit")
        self.assertIn(deposited, WAITING)
        self.assertLess(kinds.index("deposit"), self.events.index(("buy", "鑑定の巻物")))
        identified = next(name for kind, name in self.events if kind == "identify")
        self.assertIn(identified, WAITING)

    # The inherited Identify-staff scenarios belong to the life-427 fixture.
    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None


if __name__ == "__main__":
    import unittest
    unittest.main()
