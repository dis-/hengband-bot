"""The 2026-11-14 morning town stops (bot-dddf29c2f), replayed from their town arrivals.

n1-c life-207 06:29:40, town:blocked:survival:combat_weapon_ready.  The Lv47 Magic-Eater
went down Yeek cave 1F for one supply-stockout mining run (Cure Critical Wounds out of
stock), wielded two diggers ('ta' 'tb', fundraise:wield-digging-tool), found nothing and
climbed back with the same gold, experience and items.  In town the re-arm
(_town_restore_weapon_key -> combat-loadout) was refused by the equipment executor as
"goal-already-superseded": its progress core (gold, experience, item totals) equalled the
one of the mining-loadout posted in the dungeon.  The departure minimum then failed
combat_weapon_ready and the town end stopped by name on the third board of the visit.
The floor is part of the progress core now, so a re-arm after the run is not a flip.

n1-a life-522 06:31:49, town:blocked:owner-retired-burst after town:blocked:repetition.
Three Home identification takes had used the identification-withdrawal claim's budget
(3), so the ordinary router no longer walked to Home for the fourth filed take
(耐火のナイト・シールド).  The town end's filed_take_route_key walked there; Home handed
the take to its outside entrance (home:leave-for-pending-withdraw), the one board its
withdrawal is composed on, and the town end stepped off that entrance before asking
filed_take_route_key again, which walked back onto the entrance: 100 boards around
(45,123).  The filed take now answers before the entrance step-off.

n1-b life-395 06:37:50, town:blocked:owner-retired-burst.  The previous visit filed a
full-Home sale of 耐久力の指輪 (+2), then identified the ring (it became
耐久力の指輪 (+2) {+耐}) and put it back in Home.  The errand kept the old name, so at the
Home entrance its target was never observed and the pending Restore Constitution take
behind it was never composed: home-errand:target-unobserved:full-home-sale, ESC outside
the store, until the owner retirement.  A Home errand whose name the complete current
catalogue no longer holds gives way, as the identification takes already did
(c12b43110d, n1-b life-348).

Recorded: the town-arrival checkpoint and its journal
(tests/extract_town_stops_1114am_fixtures.py), decided through the public choose_key;
the re-arm is posted through the production executor (_ExecutorInputPort).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import adopt_calibration, decisions, restore
from tests.support import recorded as executor_harness

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1114am"


class Visit:
    """A fixture's arrival policy and journalled boards (calibration only when recorded)."""

    def __init__(self, name):
        source = FIXTURES / name
        self._directory = TemporaryDirectory()
        root = Path(self._directory.name)
        self.scratch = root / "scratch"
        self.scratch.mkdir()
        visit = root / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        self.journal = lzma.decompress((source / "journal.jsonl.xz").read_bytes())
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(self.journal))
        self.policy = restore(visit, self.scratch)
        self.policy._home_disposal.history_path = self.scratch / "home-history.jsonc"
        if (source / "calibration.json").is_file():
            adopt_calibration(self.policy, source / "calibration.json", self.scratch)
        self.rows = list(decisions(self.policy, visit, self.scratch))

    def board(self, row):
        entry = json.loads(self.journal.decode("utf-8").splitlines()[row])
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def close(self):
        self._directory.cleanup()

    def post(self, key):
        policy = self.policy
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class TownStops1114RecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def visit(self, name):
        visit = Visit(name)
        self.addCleanup(visit.close)
        return visit

    def test_the_town_rearms_the_weapon_after_a_fruitless_mining_run(self):
        visit = self.visit("digger-rearm-207")
        policy = visit.policy
        (recorded, supply), (stop, stop_supply) = visit.rows
        self.assertEqual(recorded["reason"], "town:recover")
        visit.post(policy.choose_key(supply()))
        self.assertEqual(stop["reason"], "town:blocked:survival:combat_weapon_ready")
        board = stop_supply()
        hands = {item.slot: item for item in board.equipment if item.slot in ("main_hand", "sub_hand")}
        self.assertTrue(all(item.is_digging_tool for item in hands.values()), hands)
        spear = next(item for item in board.inventory if item.is_melee_weapon)
        self.assertEqual(spear.name, policy._normal_weapon_name)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:restore-combat-weapon")
        self.assertTrue(key.startswith("w"), key)
        raw = visit.board(1)
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), [key])

    def test_the_filed_home_take_is_composed_on_the_entrance_home_hands_it_to(self):
        visit = self.visit("filed-take-522")
        policy = visit.policy
        for recorded, supply in visit.rows[:52]:
            key = policy.choose_key(supply())
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            visit.post(key)
        # Row 52, on another shop's entrance: the filed take walks to Home at once
        # (recorded: one step off first).  Rows 53-54 are the recorded walk and
        # Home's hand-off.
        for recorded, supply in visit.rows[52:55]:
            key = policy.choose_key(supply())
            if recorded["row"] == 52:
                self.assertEqual(policy.last_reason, "shop:travel")
            else:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
                visit.post(key)
        self.assertEqual(visit.rows[54][0]["reason"], "home:leave-for-pending-withdraw")
        recorded, supply = visit.rows[55]
        self.assertEqual(recorded["reason"], "town:entrance-step-off:town:end-step-off")
        board = supply()
        self.assertIsNone(board.store)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "home-errand:atomic-withdraw:identification-catalog")
        raw = visit.board(55)
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), [key])

    def test_a_home_sale_errand_that_outlived_its_name_gives_way(self):
        visit = self.visit("renamed-sale-395")
        policy = visit.policy
        # The arrival policy holds the sale under the ring's earlier name.
        stale = ("耐久力の指輪 (+2)", 45, 27)
        self.assertEqual(policy._home_errand.request.signature, stale)
        for recorded, supply in visit.rows[:84]:
            key = policy.choose_key(supply())
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            visit.post(key)
        self.assertEqual(visit.rows[83][0]["reason"], "home:leave-for-pending-withdraw")
        self.assertIsNone(policy._home_errand.request)
        names = {policy._item_signature(item) for item in policy._home_knowledge_items}
        self.assertNotIn(stale, names)
        self.assertIn(("耐久力の指輪 (+2) {+耐}", 45, 27), names)
        recorded, supply = visit.rows[84]
        self.assertTrue(recorded["reason"].startswith(
            "town-progress-invariant:defect:home-errand:target-unobserved:full-home-sale"))
        board = supply()
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "home:atomic-withdraw")
        self.assertIsNone(policy._home_errand.request)
        self.assertEqual(key, "5pi1\r\x1b")
        # DECLARED CONSTRUCTED: the Home screens of store.cpp for "5" (enter on the
        # entrance), "p" (get), the letter, the quantity and Escape, on the page
        # recorded on row 83.
        page = visit.board(83)["store"]
        ware = next(item for item in page["items"] if item["letter"] == "i")
        screens = [
            executor_harness.store_screen(),
            executor_harness.prompt_screen(
                f"(アイテム:a-{page['items'][-1]['letter']}, ESCで中断) どのアイテムを取りますか? "),
            executor_harness.prompt_screen(f"いくつですか (1-{ware['count']}): 1"),
            executor_harness.store_screen(),
        ]
        raw = visit.board(84)
        self.assertEqual(self.post(policy, raw, key, screens, self.later(raw)),
                         ["5", "p", "i", "1\r", "\x1b"])


if __name__ == "__main__":
    import unittest
    unittest.main()
