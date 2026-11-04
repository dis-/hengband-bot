"""The 2026-11-03 viewing-bot stops of hourly-0000-1103.

Each class pins one root on its recorded board; facts the capture keeps
outside the board are marked DECLARED RECONSTRUCTED.
Fixture: tests/extract_hourly_0000_1103_fixtures.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot import me_staff_sequence as sequence
from hengbot.town_terminal import gather_town_end, verdict_town_end
from tests import test_input_executor as executor_pins
from tests import test_me_nokey_1031_recorded as _test_me_nokey_1031_recorded
import test_hourly_0700_1102_recorded as _test_hourly_0700_1102_recorded


FIXTURE = Path(__file__).with_name("fixtures") / "hourly-0000-1103.json.gz"
TVAL_AMULET = 40
SV_CCW = 36  # 致命傷の治癒の薬 (lib/edit BaseitemDefinitions)


def _cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class OutsideEquipBeforeHomeReentryTest(_test_hourly_0700_1102_recorded.RecordedTownPolicy, executor_pins.ProductionHarness):
    """n1-c life-112 00:25:46 town:blocked:owner-retired-burst.

    In Morivant the equipment session's one action was to wear the carried
    耐電のアミュレット (pack n) on the empty neck slot, an equip outside Home.
    The town plan's first stop was Home, and the Home route (owned by the
    session, purpose equipment-work) went in (9158); inside, the session
    left with equipment-transaction:leave-home-for-equip; outside the
    identification owner identified one pack weapon, then the Home route
    waited on the entrance to go in again (9161 ``5``) before the equip.
    Three leave/identify/enter rounds later the store router had retired
    three times and the bot stopped with the amulet still in the pack.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["equip"]

    def policy(self, name):
        case = self.case
        raw = case["boards"][name]
        policy = self.primed(raw, case["home"]["knowledge"]["items"], case["skill"])
        board = self.board(policy, raw)
        (amulet,) = [item for item in board.inventory if item.tval == TVAL_AMULET]
        recorded = case["decisions"][0]
        # DECLARED RECONSTRUCTED: captures omit the session object; every
        # recorded row of the visit shows this one unposted action
        # (transaction_next) of the carried amulet, and the Home candidate
        # latch (home_candidate_waiting) that put Home first in the plan.
        action = recorded["transaction_next"]
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((EquipmentTransaction(
                **action, item_identity=equipment_identity(amulet),
                move_identity=equipment_move_identity(amulet)),), (), len(raw["inventory"])))
        policy._home_candidate_waiting = True
        return policy, board, raw

    def test_recorded_rounds(self):
        rows = {row["decision_sequence"]: row for row in self.case["decisions"]}
        self.assertEqual((rows[9158]["reason"], rows[9158]["key"]), ("shop:travel", "\x1b`n(."))
        self.assertEqual((rows[9161]["reason"], rows[9161]["key"]), ("shop:travel:await-entry", "5"))
        self.assertEqual(rows[9181]["reason"], "town:blocked:owner-retired-burst")
        for row in rows.values():
            self.assertEqual(row["transaction_next"],
                             {"phase": "equip", "kind": "equip",
                              "item_id": "pack:8486b7fecf6c8c06:0", "target_slot": "neck"})
            self.assertEqual(row["context"], "outside_home")
        self.assertEqual([rows[s]["reason"] for s in (9165, 9171, 9177)],
                         ["equipment-transaction:leave-home-for-equip"] * 3)

    def test_the_outside_equip_is_worn_before_the_home_route(self):
        for name in ("travel", "entrance"):
            with self.subTest(board=name):
                policy, board, raw = self.policy(name)
                key = policy.choose_key(board)
                # Recorded: Home travel (9158) / await-entry (9161).
                self.assertEqual((key, policy.last_reason), ("wn", "equipment-transaction:equip"))
                self.post(policy, board, raw, key)

    def post(self, policy, board, raw, key):
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        # DECLARED CONSTRUCTED: the game's equip prompt (cmd-item/
        # cmd-equipment.cpp) and the following board with the amulet worn.
        worn = copy.deepcopy(raw)
        worn["turn"] += 10
        amulet = next(item for item in worn["inventory"] if item["slot"] == "n")
        worn["inventory"].remove(amulet)
        worn["equipment"].append(dict(amulet, slot="neck"))
        game.screens = [executor_pins.prompt_screen("(持ち物: a-r, ESC) どれを装備しますか? "),
                        executor_pins.command_screen(worn["turn"])]
        game.states = [copy.deepcopy(worn) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual("".join(game.accepted), key)


class RememberedStaffListAfterRestartTest(_test_hourly_0700_1102_recorded.RecordedTownPolicy, _test_me_nokey_1031_recorded.PostedKey):
    """n1-c life-112 00:05:57 quest:blocked:me-staff.

    The process restarted on Yeek cave 8F after the 00:04 loop-detected
    stop, so the staff sequence's absorption record was empty.  On 9F the
    periodic refresh browsed the staff list (decision 467 ``bA``); after the
    recall the town board (turn 605456) went to the skill list, the Home
    scan, the dump and the wand and rod browses (544-548) while the
    sequence counted its own read attempts, and 549 stopped on
    power-list-unavailable without the sequence reading the 9F list.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["staff"]

    def test_recorded_stop(self):
        rows = {(row["decision_sequence"], row["key"]): row for row in self.case["decisions"]}
        self.assertEqual(rows[(467, "bA")]["reason"], "periodic:magic-eater-powers")
        self.assertEqual(rows[(467, "bA")]["floor"]["level"], 9)
        self.assertEqual(rows[(549, "")]["reason"], "quest:blocked:me-staff")
        stop = self.case["at_stop"]
        self.assertEqual((stop["absorbed"], stop["failure"], stop["powers_read"]),
                         ({}, "power-list-unavailable", False))

    def test_the_staff_list_browsed_on_9f_is_the_absorption_record(self):
        case = self.case
        raw = case["board"]
        policy = self.primed(raw, case["home"]["knowledge"]["items"], case["skill"])
        # DECLARED RECONSTRUCTED: the 9F browse's displayed staff list (the
        # executor's projection is not in state.jsonl): the staffs the
        # record before the restart held, as cmd-magiceat.cpp lists them;
        # and the three read attempts the visit had counted before the stop
        # board (the stop record holds the fourth).
        absorbed = {int(key.split(":")[1]): count
                    for key, count in case["before_restart"]["absorbed"].items()
                    if key.startswith("staff:")}
        policy._me_device_lists = {"staff": (604668, tuple(
            {"name": sequence.POWER_NAMES[sval][0], "current": count, "max": count,
             "fail": 5, "success": 95} for sval, count in absorbed.items()))}
        sequence.state(policy).attempts = {("read-powers", 0): 3}
        board = self.board(policy, raw)
        key = policy.choose_key(board)
        # Recorded: '' quest:blocked:me-staff.  The HP 143/193 character
        # rests in town instead.
        self.assertEqual((key, policy.last_reason), ("R&\r", "town:recover"))
        record = sequence.state(policy)
        self.assertTrue(record.powers_read)
        self.assertIsNone(record.failure)
        self.assertEqual(record.absorbed,
                         {f"staff:{sval}": count for sval, count in absorbed.items()})
        # DECLARED CONSTRUCTED: cmd-move.cpp asks the rest count.
        self.post(policy, raw, key, [executor_pins.prompt_screen(
            "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): &")])


class TempleShelfEvidenceStockoutTest(_test_hourly_0700_1102_recorded.RecordedTownPolicy, _test_me_nokey_1031_recorded.PostedKey):
    """n1-c life-112 00:34:58 town:blocked:survival:cure_critical_ready.

    Back from 18F with 5 of 10 Cure Critical Wounds potions, the visit found
    the Alchemist without them (962488).  The Temple had sold its last 10 to
    the previous visit (956577, restocked then), so the plan skipped it on
    that page (shelf-evidence), but the purchase-gap reader counted only
    suppliers visited or attempted in this visit: the stockout was not a
    purchase gap and the town end stopped instead of starting the mining
    cycle (owner 2026-11-02 「品切れも採掘に回す」).
    """

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["cure"]

    def policy(self):
        case = self.case
        raw = case["board"]
        policy = self.primed(raw, case["home"]["knowledge"]["items"], case["skill"])
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        # DECLARED RECONSTRUCTED from policy-state.json: the staff sequence
        # record (all stage staffs absorbed).
        recorded = case["sequence"]
        record = sequence.state(policy)
        record.absorbed = dict(recorded["absorbed"])
        record.bought = frozenset(recorded["bought"])
        record.stage = recorded["stage"]
        record.powers_read = True
        pages = case["pages"]
        # The two Temple pages as the shelf evidence observes them; the
        # second opens another visit (DECLARED RECONSTRUCTED: the earlier
        # page's visit identity), 23,762 game turns later: a restock.
        earlier = self.board(policy, pages["temple_before"])
        policy._observe_shelf_evidence(earlier)
        town = policy._effective_town_id(earlier)
        policy._in_store_attribute("_shelf_evidence")["pages"][(town, 3)]["opened_sequence"] = -1
        temple = self.board(policy, pages["temple"])
        policy._observe_shelf_evidence(temple)
        ccw = next(item for item in temple.store.items if item.tval == 75 and item.sval == SV_CCW)
        # DECLARED RECONSTRUCTED: the visit's recorded purchase of all ten
        # (the pack holds 10 on the next board, 956606).
        policy._note_shelf_trade(temple, 3, "buy", (ccw.name, 75, SV_CCW), ccw.count)
        # This visit: the Alchemist page and the stores the ledger records
        # as visited (departure_block.town_ledger.store_visits).
        alchemist = self.board(policy, pages["alchemist"])
        policy._town_supplier_stock[4] = alchemist.store
        policy._town_supplier_stock_observations = {4: (0, alchemist.turn)}
        for store in map(int, case["departure_block"]["town_ledger"]["store_visits"]):
            policy._town_store_attempted[store] = alchemist.turn
        return policy, self.board(policy, raw), raw

    def test_recorded_stop(self):
        case = self.case
        self.assertEqual((case["stop"]["reason"], case["departure_block"]["failed"]),
                         ("town:blocked:survival:cure_critical_ready", ["cure_critical_ready"]))
        self.assertNotIn("3", case["departure_block"]["town_ledger"]["store_visits"])
        temple = case["pages"]["temple"]["store"]["items"]
        self.assertEqual([(item["count"], item["price"]) for item in temple
                          if item["tval"] == 75 and item["sval"] == SV_CCW], [(10, 158)])
        self.assertFalse(any(item["tval"] == 75 and item["sval"] == SV_CCW
                             for item in case["pages"]["alchemist"]["store"]["items"]))
        self.assertEqual([item["count"] for item in case["board"]["inventory"]
                          if item["tval"] == 75 and item["sval"] == SV_CCW], [5])

    def test_temple_skipped_on_its_shelf_makes_the_stockout_a_purchase_gap(self):
        policy, board, raw = self.policy()
        material = gather_town_end(policy, board)
        self.assertEqual(material.purchase_gaps, ("cure_critical_ready",))
        self.assertEqual(verdict_town_end(material).kind, "mine")
        key = policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, "town:blocked:survival:cure_critical_ready")
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
