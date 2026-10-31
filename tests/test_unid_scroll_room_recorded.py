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
from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS
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

    def beyond_recorded_pages(self, reason, key):
        """Departure, or travel to a shop this visit never recorded a page of
        (the constructed replies end there)."""
        return reason.startswith(recorded.DEPARTURE) or (
            key.startswith("\x1b`n") and len(key) > 3 and key[3] in TOWN_TRAVEL_STORE_SYMBOLS
            and TOWN_TRAVEL_STORE_SYMBOLS.index(key[3]) not in self.pages)

    def test_waiting_equipment_is_shelved_and_the_scroll_bought(self):
        policy, raw = self.boundary()
        raw, _ = self.drive(policy, raw, limit=80, done=self.beyond_recorded_pages)
        kinds = [kind for kind, _ in self.events]
        deposited = next(name for kind, name in self.events if kind == "deposit")
        self.assertIn(deposited, WAITING)
        self.assertLess(kinds.index("deposit"), self.events.index(("buy", "鑑定の巻物")))
        identified = [name for kind, name in self.events if kind == "identify"]
        self.assertTrue(set(WAITING[1:]) <= set(identified), self.events)
        # Every leaf the recorded stop failed is satisfied now (the freed
        # slots also let Home hand back its 5-charge Identify staff).
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        failed = [name for name, ok in policy._town_departure_conjuncts(
            board, commit=False).items() if not ok]
        self.assertEqual(failed, [], self.events)

    # The inherited Identify-staff scenarios belong to the life-427 fixture.
    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None


if __name__ == "__main__":
    import unittest
    unittest.main()
