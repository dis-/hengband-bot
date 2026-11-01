"""D59: the 2026-11-01 n1-c life-092 town stops (Magic-Eater Lv21-22, bot-394c491c7).

13:47:59 (turn 2609774) and 13:54:41 (turn 2648425), both
town:blocked:departure-unsatisfiable; the guard retired the character on the
second.  Each stop ran the forced departure (owner 2026-10-14 「止めないを既定
に」, policy_town.force_visit_departure) and recorded a hard stop whose minimum
failed identify_staff_ready alone (jsonlog/keep-running-events.jsonl): the
minimum demanded 20 carried Identify staff charges for the 19F landing,
although the character had absorbed the Identify staff 21 times and the
ordinary departure gate counted that power (policy_supply
_identify_staff_ready).

The equipment work that left departure unready:
- 13:47: the transaction took one cloak of a Home stack of four ('pz1') and
  then could not find it to wear (equip-item-missing): the Home executor
  matched the planned stack's identity, whose count is part of it.
- 13:54: the random-teleport suppression inscribed '.' on the trident the
  open transaction was depositing; the Home deposit could not find it under
  its new name (deposit-missing) and the visit closure left
  equipment_departure_ready false for the rest of the visit.

The test attaches each recorded board to the established static-game policy
helper (tests/test_unid_deposit_recorded.py, DECLARED RECONSTRUCTED: the
visit's observed pages and Home answers are consumed through the production
response consumer).  Fixture: tests/extract_depart2_1101_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_staff_sequence
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP, PHASE_HOME_PREPARE, EquipmentTransaction, EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import SV_STAFF_IDENTIFY, TVAL_STAFF, StoreItem, StoreState, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.test_esp_threat_rest_recorded import EDIT
import tests.test_unid_deposit_recorded as recorded


FIXTURE = Path(__file__).with_name("fixtures") / "depart2-1101.json.gz"
CLOAK = "クローク [1,+0] {Q34}"
CLOAK_ID = "home:66af66797f74632f:0"


def load_cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return {case["id"].split("/")[0]: case for case in json.load(stream)}


class Depart2RecordedBase(recorded.UnidentifiedDepositRecordedTest):
    """One recorded board of life-092; subclasses name the case and board."""

    case_name = "cloak"
    board_name = "stop"

    # The inherited life-427 scenarios belong to their own fixture.
    test_recorded_stop = None
    test_waiting_equipment_is_shelved_and_the_staff_bought = None
    test_shelved_equipment_is_taken_back_and_identified_with_a_source = None

    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases()
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        case = self.cases[self.case_name]
        board = case["boards"][self.board_name]
        # The boundary consumes the visit's answers observed before the board.
        self.case = dict(case, board=board, observations=[
            row for row in case["observations"] if row["turn"] < board["turn"]])
        super().setUp()

    def boundary(self):
        policy, raw = super().boundary()
        # DECLARED RECONSTRUCTED from the capture's policy-state.json: the
        # staff sequence's record of the staffs absorbed in this life (the
        # Identify staff 21 times) and the power list read in this process.
        recorded_sequence = self.case["state"]["_me_staff_sequence"]
        record = me_staff_sequence.state(policy)
        record.absorbed = {int(sval): count for sval, count in recorded_sequence["absorbed"].items()}
        record.stage = recorded_sequence["stage"]
        record.powers_read = True
        # DECLARED RECONSTRUCTED: the supplier pages the process remembered
        # (modes_and_latches) and the dive target of the stop decision row
        # (over_extension: the Orc cave, recall landing 19F).
        for store, page in self.case["modes"]["_town_supplier_stock"].items():
            page = copy.deepcopy(page)
            for item in page["items"]:
                for name in ("known_flags", "exported_fields"):
                    item[name] = frozenset(item[name])
            page["items"] = [StoreItem(**item) for item in page["items"]]
            policy._town_supplier_stock[int(store)] = StoreState(**page)
        policy._town_supplier_stock_observations = {
            int(store): tuple(value) for store, value
            in self.case["modes"]["_town_supplier_stock_observations"].items()}
        target = self.case["decisions"][-1]["over_extension"]
        policy._target_dungeon_id = target["target_dungeon_id"]
        policy._alternate_dungeon = target["alternate_dungeon_id"]
        return policy, raw

    def decision(self, sequence):
        return next(row for row in self.case["decisions"]
                    if row["decision_sequence"] == sequence)


class ForcedDepartureAbsorbedIdentifyRecordedTest(Depart2RecordedBase):
    """Root 1: the forced departure's minimum reads the absorbed Identify staff."""

    def test_recorded_stops(self):
        for name, sequence in (("cloak", 13470), ("trident", 3061)):
            case = self.cases[name]
            last = case["decisions"][-1]
            self.assertEqual((last["decision_sequence"], last["reason"]),
                             (sequence, "town:blocked:departure-unsatisfiable"))
            (forced,) = case["keep_running"]
            self.assertEqual((forced["outcome"], forced["minimum"]["failed"],
                              forced["destination_depth"]),
                             ("hard_stop", ["identify_staff_ready"], 19))
            absorbed = case["state"]["_me_staff_sequence"]["absorbed"]
            self.assertEqual(absorbed[str(SV_STAFF_IDENTIFY)], 21)
            board = parse_snapshot(copy.deepcopy(case["boards"]["stop"]), self.monrace)
            self.assertFalse(any(item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY
                                 for item in board.inventory))
        # 13:47: the latch the 13455 terminal armed fired on the Home
        # entrance after the next Home pass (policy.py _decide, store context).
        self.assertEqual(self.cases["cloak"]["state"]["_town_blocked_reason"],
                         "departure-unsatisfiable")
        self.assertEqual(self.decision(13455)["departure_block"]["failed"],
                         ["equipment_departure_ready", "home_catalog_ready"])

    def test_latched_stop_departs_on_the_absorbed_identify_staff(self):
        policy, raw = self.boundary()
        # DECLARED RECONSTRUCTED from policy-state.json and decision 13469:
        # the terminal latch armed at decision 13455, and the previous board
        # was the Home page the character had just left.
        policy._town_blocked_reason = self.case["state"]["_town_blocked_reason"]
        policy._last_snapshot_was_store = True
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy.observe_store_screen(False)
        key = str(policy.choose_key(board))
        # Recorded: ('9', town:blocked:departure-unsatisfiable), a hard stop.
        self.assertNotEqual(policy.last_reason, "town:blocked:departure-unsatisfiable")
        self.assertEqual(policy._visit_departure_committed, "departure-unsatisfiable")
        following = self.reply(raw, key)
        self.post(policy, raw, key, following)
        # The committed departure reads Word of Recall (its dungeon prompt is
        # tests/test_recall_dungeon_prompt_recorded.py's).
        recall = next(it["slot"] for it in following["inventory"] if it["tval"] == 70
                      and it["sval"] == 11)
        raw, reasons = self.drive(policy, following, limit=12,
                                  done=lambda reason, key: key.startswith("r" + recall))
        self.assertEqual(reasons[-1], "town:repetition-depart:recall")


class TridentStopMinimumRecordedTest(Depart2RecordedBase):
    """Root 1 on the 13:54 stop board, through the CLI's forced departure."""

    case_name = "trident"

    def test_forced_departure_minimum_holds(self):
        policy, raw = self.boundary()
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy.prime(board)
        # cli._handle_owner_retirement and _town_blocked_key call this public
        # entry; the recorded call returned None (hard_stop).
        key = policy.force_visit_departure(board, "departure-unsatisfiable")
        self.assertIsNotNone(key)
        self.assertEqual(policy._visit_departure_committed, "departure-unsatisfiable")


class PartialStackEquipRecordedTest(Depart2RecordedBase):
    """Root 2: a cloak taken from a Home stack is worn, not reported missing."""

    board_name = "taken"

    def session(self):
        """DECLARED RECONSTRUCTED: the session of decisions 13420-13428.

        The decision rows name its next actions (transaction_next: withdraw,
        then equip home:66af66797f74632f:0 to outer); the identities are the
        planner's (equipment_transaction_planner) of the recorded Home stack.
        """
        stack = next(item for item in self.case["boards"]["stack"]["store"]["items"]
                     if item["name"] == CLOAK)
        item = _parse_items([stack], protocol=3)[0]
        self.assertEqual(f"home:{equipment_identity(item)}:0", CLOAK_ID)
        identities = dict(item_identity=equipment_identity(item),
                          move_identity=equipment_move_identity(item))
        plan = EquipmentTransactionPlan((
            EquipmentTransaction(PHASE_HOME_PREPARE, "withdraw", CLOAK_ID, **identities),
            EquipmentTransaction(PHASE_EQUIP, "equip", CLOAK_ID, "outer", **identities),
        ), (), len(self.case["boards"]["stack"]["inventory"]))
        session = EquipmentTransactionSession(plan, physical_context="home")
        session.index = 1  # the take was observed (decision 13427)
        return session

    def test_recorded_take(self):
        stack, taken = (self.case["boards"][name] for name in ("stack", "taken"))
        self.assertEqual([it["count"] for it in stack["store"]["items"] if it["name"] == CLOAK], [4])
        self.assertEqual([it["count"] for it in taken["store"]["items"] if it["name"] == CLOAK], [3])
        self.assertEqual([(it["slot"], it["count"]) for it in taken["inventory"]
                          if it["name"] == CLOAK], [("h", 1)])
        self.assertEqual(self.decision(13426)["key"], "5pz1\r\x1b")
        self.assertEqual(self.decision(13428)["equipment"]["transaction_next"],
                         {"phase": "equip", "kind": "equip", "item_id": CLOAK_ID,
                          "target_slot": "outer"})
        self.assertEqual(self.decision(13429)["reason"],
                         f"town:blocked:equipment-transaction:equip-item-missing:{CLOAK_ID}")

    def test_taken_cloak_is_worn_in_home(self):
        policy, raw = self.boundary()
        policy._equipment_transaction_session = self.session()
        board = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        policy.observe_store_screen(True)
        key = str(policy.choose_key(board))
        # Recorded: ('\x1b', policy:none-store-exit) with the session blocked
        # on equip-item-missing.
        self.assertEqual((key, policy.last_reason), ("wh", "equipment-transaction:equip"))
        self.assertEqual(policy._equipment_transaction_session.blockers, [])
        following = copy.deepcopy(raw)
        cloak = next(it for it in following["inventory"] if it["slot"] == "h")
        following["inventory"].remove(cloak)
        following["equipment"].append(dict(cloak, slot="outer"))
        self.post(policy, raw, key, following)


if __name__ == "__main__":
    import unittest
    unittest.main()
