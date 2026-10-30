"""2026-10-30 n1-c life-036: the Magic-Eater's mining kit had one digger.

Owner: 「シャベルを一本しか持ってないせいで魔道具術師の採掘効率が悪い」.
On the recorded General store page after the kit's first Shovel (gold 525,
ten Shovels at 96 on the shelf) the opening route went to the Alchemist,
spent the gold on 19 Treasure Detection scrolls and the first mining run
left with one Shovel and 0 gold.  calc_skill_dig counts each wielded
digger's TUNNEL pval*20 plus each hand's weight/10, so the recorded STR
index 17 (adj_str_dig 12) digs 12+20+6=38 with one Shovel and 64 with two
(the recorded skill ratings 38 and 64).

The case starts on that recorded board with the recorded shelves
(tests/extract_me_two_diggers.py).  Only replies to newly posted keys are
constructed (tests/test_me_town_stops_recorded.py); every decision goes
through the public chooser and the production executor.
"""
import tests  # noqa: F401

import copy
import gzip
import json
from pathlib import Path

from hengbot.model import parse_snapshot
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_town_stops_recorded as me
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "me-two-diggers-20261030.json.gz"
SHOVEL = "シャベル (1d2) (+0,+0) (+1) {+掘}"
DETECTION = "財宝感知の巻物"


class MagicEaterTwoDiggersTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post
    reply = me.MagicEaterTownStopsRecordedTest.reply

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)[0]

    def boundary(self, change=None):
        case = self.case
        raw = copy.deepcopy(case["board"])
        if change is not None:
            change(raw)
        policy, raw = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces=case["monraces"], snapshot=raw, knowledge=case["knowledge"],
            state={"modes_and_latches": {}}))
        # DECLARED RECONSTRUCTED: the capture's policy state is from the end
        # of the life; the supplier census is rebuilt from the pages this
        # same ring observed earlier in this visit (Black market: both pages).
        policy._opening_q1_shelves = {}
        for store, tops in case["pages"].items():
            if store == "0":
                continue  # The board itself is the General store page.
            pages = []
            for _, page in sorted(tops.items(), key=lambda row: int(row[0])):
                view = copy.deepcopy(raw)
                view["store"] = page
                pages.append(parse_snapshot(view, policy._monrace_knowledge).store)
            first = pages[0]
            policy._town_supplier_stock[int(store)] = first
            policy._town_supplier_stock_observations[int(store)] = (0, raw["turn"])
            policy._opening_q1_shelves[int(store)] = dict(
                town=0, entry=-1, stock_num=first.stock_num, visits={},
                pages={page.page_top: page for page in pages},
                complete=len(pages) * first.page_size >= first.stock_num)
        return policy, raw

    def drive(self, policy, raw, limit=60):
        """Run until the kit is done and the route heads for the Q1 request."""
        self.pages = {store: tops["0"] for store, tops in self.case["pages"].items()}
        self.bought, keys = [], []
        for _ in range(limit):
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            keys.append((key, policy.last_reason))
            if policy.last_reason == "fixedquest:request:approach":
                return raw, keys
            self.assertNotEqual(key, "", keys[-6:])
            self.assertFalse(policy.last_reason.startswith(me.STOPS), keys[-6:])
            following = self.reply(policy, raw, key, self.case)
            self.post(policy, raw, key, following)
            raw = following
        self.fail(("no progress", self.bought, keys[-10:]))

    def test_recorded_kit_left_with_one_shovel(self):
        recorded = self.case["recorded"]
        self.assertEqual(recorded["next_purchases"][:2], [[82075, 4, 525], [82075, 4, 69]])
        self.assertEqual((recorded["departure"]["gold"], recorded["departure"]["diggers"]),
                         (0, [SHOVEL]))
        shelf = [it for it in self.case["board"]["store"]["items"] if it["tval"] == 20]
        self.assertIn((SHOVEL, 96, 10), [(it["name"], it["price"], it["count"]) for it in shelf])

    def test_magic_eater_buys_the_second_shovel_before_detection(self):
        policy, raw = self.boundary()
        raw, keys = self.drive(policy, raw)
        self.assertIn(("pl1\r\r\x1b", "shop:one-shot-buy"), keys)
        self.assertEqual(self.bought[0], (SHOVEL, 1))
        self.assertEqual([name for name, _ in self.bought[1:]], [DETECTION])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(policy._digging_tool_count(board), 2)
        self.assertGreater(policy._count_treasure_detection_scrolls(board), 0)

    def test_short_gold_keeps_the_minimum_kit(self):
        # DECLARED CONSTRUCTED: one gold short of Shovel + one scroll; the
        # second digger waits for the fundraising target on the next visit.
        def short(raw):
            raw["player"]["gold"] = 96 + 24 - 1
        policy, raw = self.boundary(short)
        raw, _ = self.drive(policy, raw)
        self.assertEqual([name for name, _ in self.bought], [DETECTION])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(policy._digging_tool_count(board), 1)

    def test_other_classes_keep_the_one_digger_kit(self):
        # DECLARED CONSTRUCTED: the same board and shelves as a Warrior
        # (class 0), asked for the second-digger choice the plan makes.
        for class_id, expected in ((16, SHOVEL), (0, None)):
            with self.subTest(class_id=class_id):
                def change(raw):
                    raw["player"]["class_id"] = class_id
                policy, raw = self.boundary(change)
                board = parse_snapshot(raw, policy._monrace_knowledge)
                offers = [(0, it) for it in board.store.items if it.count > 0] + [
                    (4, it) for it in policy._town_supplier_stock[4].items if it.count > 0]
                diggers = [row for row in offers if row[1].is_digging_tool]
                owned = [it for it in board.inventory if it.is_digging_tool]
                second = policy._opening_q1_second_digger(board, diggers, owned, offers)
                self.assertEqual(second and second[1].name, expected)


if __name__ == "__main__":
    import unittest
    unittest.main()
