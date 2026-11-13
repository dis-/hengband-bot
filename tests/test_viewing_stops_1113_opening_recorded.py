"""The opening route (owner 2026-10-26: Q34 -> mining kit -> Q1) on the 2026-11-13 stops.

* afraid-385 -- n1-b life-385, Lv6 Magic-Eater, 08:44:13: afraid at full HP (108/108) in
  the Outpost with the Q1 carries ready; readiness refused Q1 as temporary-status and the
  route stopped as quest:blocked:opening-route (readiness:...temporary-status), and again
  on the same board after each restart, so the character was replaced.  The route rested
  only below full HP; rest-as-needed also waits out fear (PlayerType::is_fully_healthy,
  src/system/player-type-definition.cpp:75-91; bot-json-output.cpp:875 exports only the
  timed fear).
* shelf-387 -- n1-b life-387, Lv6 Magic-Eater, 12:30:22: back from Q34 with 14 lit
  torches and 155 gold; the General Store's shelf held four torches, short of the 20
  the Magic-Eater carries to Q1, so the route stopped as stop:stock:quest-throwing-items
  without buying them.  The QUEST_1 carry_floor (「携行品を全部は買えない時の下限」,
  owner 2026-10-31 「Q1の要求値を下げ、受注可能にする」, Magic-Eater floor 9) lowers a
  carry the gold cannot buy; a short shelf now lowers it the same way.

Recorded: each capture's town-arrival checkpoint, calibration and journal
(tests/extract_viewing_stops_1113_fixtures.py), decided through the public choose_key;
the new key is posted through the production executor (_ExecutorInputPort).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot.model import parse_snapshot
from hengbot.policy_constants import REST_MACRO
from tests.support import recorded as executor_harness
from tests import test_q2_damage_ammo_1102_recorded as q2_ammo
from test_me_stops_1103_recorded import Visit

FIXTURES = Path(__file__).with_name("fixtures") / "viewing-stops-1113"
STOP = "quest:blocked:opening-route"
REST_PROMPT = "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): "
STORE_ROW = 16   # opening-387: the General Store's page, recorded shop:observe-and-leave


def journal_board(name, row):
    """The raw board of a journalled decision (replay_town_arrival.decisions)."""
    entries = lzma.decompress((FIXTURES / name / "journal.jsonl.xz").read_bytes())
    entry = json.loads(entries.decode("utf-8").splitlines()[row])
    return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])


class OpeningRouteStops1113Test(executor_harness.RecordedHarness):
    post_buy = q2_ammo.Q2DamageAmmoRecordedTest.post_buy
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def visit(self, name):
        visit = Visit((FIXTURES / name).resolve())
        visit.policy._home_disposal.history_path = visit.scratch / "home-history.jsonc"
        self.addCleanup(visit.close)
        return visit

    def rest_through_executor(self, policy, board, key):
        raw = {"turn": board.turn, "grid_map": {"runs": []}}
        # DECLARED CONSTRUCTED: the rest-count prompt (cmd-move.cpp:445) and the map after it.
        prompt = executor_harness.prompt_screen(REST_PROMPT + "&")
        return self.post(policy, raw, key, [prompt], dict(raw, turn=board.turn + 10))

    def test_fear_at_full_hp_is_rested_out_before_q1(self):
        visit = self.visit("opening-385")
        policy = visit.policy
        rows = list(visit.rows)
        divergent = []
        for recorded, supply in rows[:-1]:
            key = policy.choose_key(supply())
            if (key, policy.last_reason) != (recorded["key"], recorded["reason"]):
                divergent.append(recorded["row"])
            # The game did what was recorded: post the recorded key.
            visit.post(recorded["key"])
        # Rows 18-27 are a cloak's equipment transaction that the replayed
        # calibration does not reach (the live one ended at
        # confirmation-stall-bound with nothing applied); the boards re-join
        # the recording from row 28 on.
        self.assertTrue(set(divergent) <= set(range(18, 28)), divergent)
        recorded, supply = rows[-1]
        board = supply()
        self.assertEqual((recorded["key"], recorded["reason"]), ("", STOP))
        self.assertTrue(board.player.afraid)
        self.assertEqual(board.player.hp, board.player.max_hp)
        self.assertFalse(board.visible_monsters)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (REST_MACRO, "town:recover"))
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None))
        self.assertEqual(self.rest_through_executor(policy, board, key), ["R", REST_MACRO[1:]])

    def test_a_short_torch_shelf_lowers_the_carry_and_is_bought(self):
        visit = self.visit("opening-387")
        policy = visit.policy
        rows = list(visit.rows)
        for recorded, supply in rows[:STORE_ROW]:
            key = policy.choose_key(supply())
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            visit.post(key)
        recorded, supply = rows[STORE_ROW]
        self.assertEqual((recorded["key"], recorded["reason"]), ("\x1b", "shop:observe-and-leave"))
        self.assertEqual(rows[-1][0]["reason"], STOP)
        board = supply()
        torches = [item for item in board.store.items if item.is_torch]
        self.assertEqual([(item.count, item.price) for item in torches], [(4, 3)])
        self.assertEqual((policy._count_throwing_torches(board), board.player.gold), (14, 155))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         (f"p{torches[0].letter}4\r\r", "shop:in-store-buy"))
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None))
        # Lowered to what the gold and the shelf allow (14 + 4), above the floor 9.
        self.assertEqual(policy._opening_q1_requirements(board)[0][1], 18)
        self.monraces = policy._monrace_knowledge
        raw = journal_board("opening-387", STORE_ROW)
        game = self.post_buy(policy, raw, key)
        self.assertEqual(game.accepted, ["p", torches[0].letter, "4\r", "\r"])

    def test_the_lowered_torches_meet_q1_readiness(self):
        visit = self.visit("opening-387")
        policy = visit.policy
        rows = list(visit.rows)
        for recorded, supply in rows[:STORE_ROW]:
            visit.post(policy.choose_key(supply()))
        board = rows[STORE_ROW][1]()
        visit.post(policy.choose_key(board))   # the four torches (the test above)
        # DECLARED CONSTRUCTED: the shelf after the four torches were bought.
        raw = copy.deepcopy(journal_board("opening-387", STORE_ROW))
        bought = next(item for item in raw["store"]["items"] if item["tval"] == 39 and item["sval"] == 0)
        raw["store"]["items"].remove(bought)
        raw["store"]["stock_num"] -= 1
        raw["player"]["gold"] -= 4 * bought["price"]
        stack = next(item for item in raw["inventory"] if item["tval"] == 39 and item["count"] == 9)
        stack["count"] += 4
        raw["turn"] += 1
        after = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(policy._count_throwing_torches(after), 18)
        key = policy.choose_key(after)
        self.assertNotEqual(policy.last_reason, STOP, key)
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None))
        self.assertEqual(policy._opening_q1_requirements(after)[0][1], 18)
        self.assertTrue(policy._fixed_quest_ready(after, 1), policy.fixed_quest_readiness_state())


if __name__ == "__main__":
    unittest.main()
