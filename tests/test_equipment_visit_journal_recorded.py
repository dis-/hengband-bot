"""The town visit's equipment journal and the settlement of a slot's round trip (review 11-22 E0).

Owner 2026-11-22 「決まりは足さず、着け直しを記録。往復が起きたら停止して直す。」 and (verbatim)
「1往復で決定するなら止める必要はない」: one round trip that settles is recorded; the slot's
second round trip in the visit stopped until supervisor 2026-11-28 (n1-c life-224): it now closes
the visit's equipment transaction and keeps the worn kit (``settle``), nothing stops.

Recorded round trips (both in town, one visit each):

- tests/fixtures/equip-swap-20260826 (the 2026-08-26 equip-swap loop): the body slot went
  硬革よろい -> (off) -> 鎖かたびら (board 230) -> 硬革よろい (board 237, the first round trip) ->
  (off) -> 汚れたボロ服 (275) -> 硬革よろい (282, the second).  The boards 208-283 are decided
  through the public ``choose_key`` by a fresh policy (as test_equipment_swap_loop_incident does
  with the same boards): no decision stops (board 237 included: recorded, ``stops`` false), and
  board 282 closes the visit's equipment transaction (``SETTLED_CLOSURE``) and decides on.
- tests/fixtures/equipment-alternation-20261005: main_hand シャベル -> (off) -> ソウルソード (4658)
  -> シャベル (4660), sub_hand シャベル -> (off) -> シャベル (the same item back: no round trip).
  One round trip: recorded, no stop.
  DECLARED: these boards are read by the journal directly (``observe`` / ``settle``, the two
  calls ``choose_key`` and ``_choose_key`` make); a fresh policy cannot decide them (the ~f
  skill list of the capture is not in it).

A normal visit with a single swap does not stop: boards 208-236 of the first (硬革 -> 鎖) and
4655-4659 of the second (シャベル -> ソウルソード); and the production transaction's own takeoff and
wear ('th', 'wj') on the 08-26 Home-door board are recorded with the writer that posted them.
"""
import tests  # noqa: F401 -- isolate runtime files

import contextlib
import gzip
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import equipment_visit_journal as journal
from hengbot.cli import _policy_final_stop_required
from hengbot.equipment_transaction_planner import PHASE_EQUIP, EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.flight_recorder import policy_state
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURES = Path(__file__).with_name("fixtures")
SNAPSHOTS_0826 = FIXTURES / "equip-swap-20260826.snapshots.jsonl.gz"
ALTERNATION_1005 = FIXTURES / "equipment-alternation-20261005.json.gz"
FIRST, CHAIN_MAIL_WORN, HARD_LEATHER_BACK, RAG_WORN, HARD_LEATHER_AGAIN, LAST = (
    208, 230, 237, 275, 282, 283)
HARD_LEATHER = "硬革よろい (-1) [6,+5]"
RAG_NAME = "汚れたボロ服 [1,+6]"
RAG = "8cc0213094bf60d5"
HARD_ARMOUR = "ba9b081829fa4479"


def boards_0826():
    with gzip.open(SNAPSHOTS_0826, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    return {index: rows[index] for index in range(FIRST, LAST + 1)}


def decide_0826(raw, path=None):
    policy = HengbotPolicy()
    policy._equipment_journal_path = path
    decided = {}
    for index, row in raw.items():
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            key = policy.choose_key(parse_snapshot(row, {}))
        decided[index] = (key, policy.last_reason, _policy_final_stop_required(policy))
    return policy, decided


class SlotRoundTripSettlesRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = boards_0826()
        cls.scratch = TemporaryDirectory()
        cls.path = Path(cls.scratch.name) / journal.FILE_NAME
        cls.policy, cls.decided = decide_0826(cls.raw, cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_recorded_boards_round_trip_twice(self):
        bodies = [next((item["name"] for item in self.raw[index]["equipment"]
                        if item["slot"] == "body"), None)
                  for index in (FIRST, CHAIN_MAIL_WORN - 1, CHAIN_MAIL_WORN, HARD_LEATHER_BACK,
                                RAG_WORN - 1, RAG_WORN, HARD_LEATHER_AGAIN, LAST)]
        self.assertEqual(bodies, [HARD_LEATHER, None, "鎖かたびら (-2) [14,+0]", HARD_LEATHER,
                                  None, RAG_NAME, HARD_LEATHER, None])

    def test_no_round_trip_stops(self):
        """On ee98f4ca21 board 237 (the first A, B, A) stopped and sent nothing; until
        supervisor 2026-11-28 board 282 (the second) did."""
        for index in range(FIRST, LAST + 1):
            self.assertFalse(self.decided[index][2], (index, self.decided[index]))
            self.assertIsNotNone(self.decided[index][0], index)
            self.assertFalse(str(self.decided[index][1]).startswith("town:blocked:equipment-slot-flipflop:"), index)

    def test_the_second_round_trip_closes_the_visits_transaction(self):
        closure = self.policy._equipment_transaction_visit_closure
        self.assertEqual((closure["reason"], closure["slot"]), (journal.SETTLED_CLOSURE, "body"))
        self.assertEqual(closure["epoch"], self.policy._town_visit_epoch)
        self.assertEqual(closure["turn"], self.raw[HARD_LEATHER_AGAIN]["turn"])

    def test_the_stop_context_and_the_file_hold_the_visit(self):
        kinds = [row["kind"] for row in self.policy._equipment_visit_journal["rows"]]
        self.assertEqual(kinds, [journal.REWEAR_EVENT, "equipment-slot-flipflop:body"] * 2
                         + [journal.FLIPFLOP_SETTLED_EVENT])
        captured = policy_state(self.policy)["state"]["_equipment_visit_journal"]
        self.assertEqual(captured["settle"]["name"], journal.ROUND_TRIP_PREFIX + "body")
        flips = [row for row in captured["rows"] if row["kind"] == "equipment-slot-flipflop:body"]
        self.assertEqual([(row["round_trip"], row["stops"]) for row in flips],
                         [(1, False), (2, True)])
        for flip in flips:
            self.assertEqual(flip["item"]["name"], HARD_LEATHER)
            self.assertEqual(flip["trail"][0], flip["trail"][2])
            self.assertNotEqual(flip["trail"][0], flip["trail"][1])
        # B: the 鎖かたびら the first time, the 汚れたボロ服 the second.
        self.assertNotEqual(flips[0]["trail"][1], flips[1]["trail"][1])
        written = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["kind"] for row in written], kinds)
        self.assertTrue(captured["settled"])


class TwoHandRoundTripRecordedTest(unittest.TestCase):
    def test_one_round_trip_of_the_shovel_is_recorded_without_a_stop(self):
        """On ee98f4ca21 board 4660 (the shovel back in main_hand) stopped."""
        data = json.loads(gzip.decompress(ALTERNATION_1005.read_bytes()))
        policy = HengbotPolicy()
        held = {}
        for sequence in range(4655, 4661):
            row = data["rows"][str(sequence)]
            raw = data["boards"][str(row["turn"])]
            board = parse_snapshot({**raw, "visible_monsters": [], "detected_monsters": []})
            self.assertTrue(board.in_town)
            policy._town_visit_epoch = data["rows"]["4655"]["turn"]
            journal.observe(policy, board)
            held[sequence] = journal.journal(policy).get("settle")
        self.assertEqual(held, {n: None for n in range(4655, 4661)})
        rows = policy._equipment_visit_journal["rows"]
        self.assertEqual([(row["kind"], row["slot"]) for row in rows],
                         [(journal.REWEAR_EVENT, "sub_hand"), (journal.REWEAR_EVENT, "main_hand"),
                          ("equipment-slot-flipflop:main_hand", "main_hand")])
        self.assertEqual((rows[-1]["round_trip"], rows[-1]["stops"]), (1, False))
        self.assertIsNone(policy._equipment_visit_journal["settle"])


class WearPostRecordTest(unittest.TestCase):
    def test_the_transactions_takeoff_and_wear_name_their_writer(self):
        from tests.test_equipment_swap_loop_incident import EquipmentSwapLoopIncidentTest as Incident
        Incident.setUpClass()
        incident = Incident("test_captured_window_replay_cannot_recur_or_swap_armour_twice")
        board = incident._surface(1172858, HARD_ARMOUR)
        actions = (EquipmentTransaction(PHASE_EQUIP, "takeoff", "hard", "body", HARD_ARMOUR),
                   EquipmentTransaction(PHASE_EQUIP, "equip", "rag", "body", RAG))
        policy = HengbotPolicy()
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan(actions, (), 0))
        keys = []
        for _ in range(3):
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            keys.append((key, policy.last_reason))
            session = policy._equipment_transaction_session
            action = None if session is None else (
                session.prepared_action or session.pending_action or session.current_action)
            policy.confirm_key_posted(key)
            board = incident._apply_posted_key(board, key, action)
        self.assertEqual(keys[:2], [("th", "equipment-transaction:takeoff"),
                                    ("wj", "equipment-transaction:equip")])
        self.assertFalse(journal.is_stop(keys[2][1]))
        posts = [row for row in policy._equipment_visit_journal["rows"] if row["kind"] == "post"]
        self.assertEqual([(row["key"], row["command"], row["slot"], row["goal"], row["item"]["name"])
                          for row in posts],
                         [("th", "takeoff", "body", "transaction-apply", HARD_LEATHER),
                          ("wj", "wield", "body", "transaction-apply", "汚れたボロ服 [1,+6]")])
        for row in posts:
            self.assertTrue(row["writer"].startswith("policy_equipment:_equipment_transaction_town_key:"),
                            row["writer"])


class SearchReasonTest(unittest.TestCase):
    def test_the_changed_signature_fields_are_named(self):
        before = (("cat-a",), (), True, (("body", "x"),), (), ("random-teleport-suppressed", ()))
        after = (("cat-a",), (), True, (("body", "y"),), (),
                 ("random-teleport-suppressed", ()), ("destination-floor", 30))
        changed, detail = journal.signature_changes(before, after)
        self.assertEqual(changed, ["worn", "destination-floor"])
        self.assertEqual(detail["worn_added"], [("body", "y")])
        self.assertEqual(journal.signature_changes(None, after), (["no-previous"], {}))

    def test_a_recorded_visits_search_is_recorded_and_its_keys_unchanged(self):
        from support.town_arrival_fixture import load
        with TemporaryDirectory() as raw:
            policy, _journal, steps = load(FIXTURES / "n1b-413-launcher-1121", Path(raw))
            for recorded, supply in steps[:10]:
                board = supply()
                with contextlib.redirect_stdout(io.StringIO()):
                    key = policy.choose_key(board)
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])
                if recorded["key"]:
                    policy.confirm_key_posted(recorded["key"])
            policy._home_disposal.history_path.unlink(missing_ok=True)
        searches = [row for row in policy._equipment_visit_journal["rows"] if row["kind"] == "search"]
        self.assertEqual(len(searches), 1)
        self.assertEqual(searches[0]["changed"], ["no-previous"])
        self.assertTrue(searches[0]["target_added"])
        self.assertIsNone(policy._equipment_visit_journal["settle"])


if __name__ == "__main__":
    unittest.main()
