"""#47: the recorded n1-c Magic-Eater no-key-exhausted stops of 2026-10-31.

Boards, knowledge rows and decision rows are frozen in
tests/fixtures/me-nokey-20261031.json.gz (tests/extract_me_nokey_1031.py).
Every decision goes through the public ``choose_key``; posted keys go
through the production executor, and the driver stop through ``_run_follow``.

DECLARED RECONSTRUCTED: the staff sequence record of each policy is the
server incident capture's ``_me_staff_sequence`` (RECORDED_SEQUENCE in the
fixture); a case states which of its fields it changes.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from hengbot import me_staff_sequence as sequence
from hengbot.cli import (
    SendResult, _ExecutorInputPort, _build_argument_parser, _run_follow, _transport_key,
)
from hengbot.flight_recorder import policy_state
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import ConservativePolicy
from tests import test_input_executor as harness
from tests import test_lv7_town_stop_recorded as lv7
from tests.test_input_executor import FaithfulHookGame, command_screen


FIXTURE = Path(__file__).with_name("fixtures") / "me-nokey-20261031.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)


def staff_board(index):
    """Ring row 104 + index of the 061452 capture."""
    return copy.deepcopy(CASE["staff"]["boards"][index])


def new_policy(raw):
    """A new process's policy primed on ``raw``, with the frozen race facts."""
    from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
    policy = ConservativePolicy()
    for race, facts in CASE["monraces"].items():
        facts = copy.deepcopy(facts)
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
        policy._monrace_knowledge[int(race)] = MonraceKnowledge(**facts)
    policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
    return policy


def skill_for(raw):
    """The recorded life-054 ~f reply (Lv14, ring row 83) for this board.

    DECLARED CONSTRUCTED for the 072115 board (Lv17, no ~f row in its ring):
    the same reply with the board's level and turn.
    """
    skill = copy.deepcopy(CASE["staff"]["skill"])
    skill["player"] = dict(skill["player"], level=raw["player"]["level"])
    return dict(skill, turn=raw["turn"])


def staff_policy(raw, *, record=True, **changes):
    policy = new_policy(raw)
    policy.consume_skill_knowledge(skill_for(raw))
    if record:
        # DECLARED RECONSTRUCTED (module docstring); ``changes`` override.
        recorded = {**CASE["recorded_sequence"], "failure": None, **changes}
        state = sequence.state(policy)
        state.absorbed = {int(sval): count for sval, count in recorded["absorbed"].items()}
        state.bought = frozenset(recorded["bought"])
        state.completed_stages = {int(k): v for k, v in recorded["completed_stages"].items()}
        state.fundraise_runs = recorded["fundraise_runs"]
        state.reached_runs = recorded["reached_runs"]
        state.fundraise_why = recorded["fundraise_why"]
        state.shelf_after_turn = recorded["shelf_after_turn"]
        state.stage = recorded["stage"]
        state.failure = recorded["failure"]
        state.powers_read = True  # the recorded process had read its absorptions
        # DECLARED CONSTRUCTED: the carried Stone to Mud wand (12 charges) as
        # already absorbed, so these staff cases are not taken over by its
        # own Tower trip (owner 2026-10-31 18h, test_me_absorbed_substitutes).
        state.absorbed["stone-to-mud"] = 12
    return policy


def decide(policy, raw, skill=None):
    board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
    key = str(policy.choose_key(board))
    if key.startswith("~f") and skill is not None:
        # DECLARED CONSTRUCTED: the recorded ~f reply answers the re-request.
        policy.consume_skill_knowledge(dict(copy.deepcopy(skill), turn=raw["turn"]))
        key = str(policy.choose_key(board))
    return key


def without_staffs(raw, svals):
    raw = copy.deepcopy(raw)
    if "inventory" in raw:
        raw["inventory"] = [item for item in raw["inventory"]
                            if not (item["tval"] == 55 and item["sval"] in svals)]
    return raw


def drive_staff_boards(policy, last, absorbed=()):
    """Ring rows 104..104+last through choose_key, as the recorded run saw them.

    DECLARED CONSTRUCTED (``absorbed``): those staffs are taken out of the
    pack, as 'G' consumes the absorbed device (mind-magic-eater.cpp).
    """
    key = None
    for raw in CASE["staff"]["boards"][:last + 1]:
        raw = without_staffs(raw, absorbed)
        if raw["type"] == "knowledge":
            policy.consume_home_knowledge(
                tuple(_parse_items(raw["knowledge"]["items"], protocol=3)))
            continue
        key = decide(policy, raw, CASE["staff"]["skill"])
        policy.confirm_key_posted(key) if key else None
    return key


class PostedKey(harness.ProductionHarness):
    def post(self, policy, raw, key):
        """Send ``key`` through the production executor on ``raw``."""
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))


class NamedFinalStopTest(unittest.TestCase):
    """R0: a policy final stop sent as "" is that stop, not no-key-exhausted."""

    def test_capture_pins_the_recorded_stop(self):
        stop = CASE["staff"]["stop"]
        self.assertEqual((stop["reason"], stop["key"]), ("quest:blocked:me-staff", ""))
        self.assertEqual(CASE["recorded_sequence"]["failure"],
                         "fundraise-target-drift:staff-stockout:2530")
        opening = CASE["opening"]["stop"]
        self.assertEqual((opening["reason"], opening["key"]), ("quest:blocked:opening-route", ""))
        self.assertEqual(opening["fixedquest_readiness"]["opening_route_failure"],
                         "stop:unaffordable-quest-reserve")

    def test_driver_stops_on_the_named_staff_stop(self):
        # The recorded board after the Magic shop (ring row 108) with the
        # recorded failure: the sequence re-declares its stop with "".
        raw = staff_board(4)
        policy = staff_policy(raw, failure=CASE["recorded_sequence"]["failure"])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.jsonl"
            state_path.write_text(json.dumps(staff_board(3)) + "\n", encoding="utf-8")
            args = _build_argument_parser().parse_args([
                "--state-file", str(state_path),
                "--decision-log", str(root / "decisions.jsonl"),
                "--poll-interval", "0.001", "--stall-timeout", "0.01",
                "--dump-interval-seconds", "0",
            ])
            args.wait_telemetry = Mock()
            appended = False

            def append_board():
                # _run_follow seeks to EOF; the board arrives on its first pass.
                nonlocal appended
                if not appended:
                    appended = True
                    with state_path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(raw) + "\n")

            with (
                patch("hengbot.cli._arm_decision_watchdog", side_effect=append_board),
                patch("hengbot.cli._append_capture_ledger"),
                patch("hengbot.cli._freeze_incident_safely") as freeze,
                patch("builtins.print") as output,
            ):
                result = _run_follow(args, policy, lambda *_a, **_k: self.fail("posted a key"),
                                     policy._monrace_knowledge)
            rows = [json.loads(line) for line in
                    (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(result, 0)
        self.assertEqual([(row["reason"], row["key"]) for row in rows if "reason" in row],
                         [("quest:blocked:me-staff", "")])
        self.assertEqual(freeze.call_args.args[1], "quest:blocked:me-staff")
        printed = [str(call.args[0]) for call in output.call_args_list if call.args]
        self.assertTrue(any(line.startswith("<quest:blocked:me-staff> ") for line in printed))
        self.assertFalse(any(line.startswith("<no-key-exhausted>") for line in printed))

    def test_incident_policy_state_keeps_the_opening_route_failure(self):
        policy = ConservativePolicy()
        policy._opening_q1_failure = "stop:unaffordable-quest-reserve"
        self.assertEqual(policy_state(policy)["state"]["_opening_q1_failure"],
                         "stop:unaffordable-quest-reserve")


class StaffStockoutTest(PostedKey):
    """鍵1a: stage 2's fifth staff out of stock with four carried (life-054 061452).

    Owner 2026-10-31 「持っている分を先に取り込む」: the carried staffs go to the
    Tower now; the stock-out waits do not count toward the run limit.
    """

    def test_capture_pins_four_carried_staffs_and_no_detect_evil(self):
        shelf = {(item["tval"], item["sval"]) for item in staff_board(1)["store"]["items"]}
        self.assertNotIn((55, sequence.SV_STAFF_DETECT_EVIL), shelf)
        carried = sorted(item["sval"] for item in staff_board(4)["inventory"] if item["tval"] == 55)
        self.assertEqual(carried, [sequence.SV_STAFF_LITE, sequence.SV_STAFF_MAPPING,
                                   sequence.SV_STAFF_DETECT_TRAP, sequence.SV_STAFF_DETECT_DOOR])
        self.assertEqual(staff_board(4)["player"]["gold"], 60981)

    def test_carried_staffs_go_to_the_tower_while_the_fifth_is_out_of_stock(self):
        # The recorded record (six reached stock-out runs); unfixed, the board
        # after the Magic shop stopped with fundraise-target-drift.
        policy = staff_policy(staff_board(0))
        key = drive_staff_boards(policy, 4)
        self.assertIsNone(sequence.state(policy).failure)
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant", key)
        self.assertNotEqual(key, "")
        self.post(policy, staff_board(4), key)

    def test_stockout_wait_is_not_counted_toward_the_run_limit(self):
        # DECLARED CONSTRUCTED: the four carried staffs already absorbed, so
        # only Detect Evil remains and nothing is carried for the Tower.
        absorbed = {**CASE["recorded_sequence"]["absorbed"],
                    **{str(sval): 9 for sval in (8, 9, 12, 13)}}
        policy = staff_policy(staff_board(0), absorbed=absorbed)
        # DECLARED CONSTRUCTED: the other towns' Magic shelves were already
        # seen without Detect Evil in this restock wait, so the spare gold
        # has nowhere left to search (test_me_staff_search_towns_recorded).
        sequence.state(policy).searched_towns.update(
            {town: staff_board(0)["turn"] for town in (1, 2, 3)})
        key = drive_staff_boards(policy, 4, absorbed=(8, 9, 12, 13))
        record = sequence.state(policy)
        self.assertIsNone(record.failure)
        self.assertIn("me-staff:fundraise:staff-stockout:", policy.last_reason, key)
        self.assertEqual((record.fundraise_runs, record.reached_runs), (6, 6))
        # The run comes back with its gold target met: still not counted.
        policy._fundraising_mode = None
        decide(policy, without_staffs(staff_board(4), (8, 9, 12, 13)), CASE["staff"]["skill"])
        self.assertIsNone(record.fundraise_target)  # the returned run was settled
        self.assertEqual((record.fundraise_runs, record.reached_runs), (6, 6))
        self.assertIsNone(record.failure)


class RestartForgetsAbsorptionsTest(PostedKey):
    """鍵1b: a restarted process read no absorption (life-054 06:14 / 07:18 / 07:21).

    The new process sold the carried stage-2 staffs and bought the absorbed
    Identify and Treasure staffs again (bot-economy.jsonl), against 「2本目は
    買わない」.  The board here is the recorded visit to the same Magic shop
    with the same pack just before the 06:14 stop (the restart board itself
    is not in the copied captures); the policy is new, without a sequence
    record, as after a restart.
    """

    # DECLARED CONSTRUCTED: the game's staff list as cmd-magiceat.cpp prints
    # the two recorded absorptions (RECORDED_SEQUENCE absorbed 5: 21, 10: 19).
    ABSORBED = {"staff": {sequence.SV_STAFF_IDENTIFY: ("鑑定", 21, 21, 5),
                          sequence.SV_STAFF_DETECT_GOLD: ("財宝感知", 19, 19, 5)},
                "wand": {}, "rod": {}}

    def read_list(self, policy, key):
        """Post the browse through the production executor; return its list."""
        from tests.test_me_powers_refresh import BrowseGame
        game = BrowseGame(self.ABSORBED)
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.commands, ["b"])
        listed = executor.ready_board["_magic_eater_power_list"]
        self.assertEqual([row["name"] for row in listed["rows"]], ["鑑定", "財宝感知"])
        return listed

    def test_new_process_reads_the_power_list_before_any_staff_trade(self):
        policy = staff_policy(staff_board(0), record=False)
        key = decide(policy, staff_board(0), CASE["staff"]["skill"])
        self.assertEqual((key, policy.last_reason), ("bA", "me-staff:read-powers"))
        listed = self.read_list(policy, key)
        policy.confirm_key_posted(key)
        sold, bought = [], []
        for index, raw in enumerate(CASE["staff"]["boards"]):
            raw = copy.deepcopy(raw)
            if raw["type"] == "knowledge":
                policy.consume_home_knowledge(
                    tuple(_parse_items(raw["knowledge"]["items"], protocol=3)))
                continue
            if index == 0:
                raw["_magic_eater_power_list"] = listed  # the browse's reply board
            key = decide(policy, raw, CASE["staff"]["skill"])
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            staffs = {item.slot: item.sval for item in board.inventory if item.tval == 55}
            # Unfixed: '{j@0' inscribed the Light staff for sale, the Home
            # deposit 'dmdldk' shelved three more, and stage 1 started over.
            if key[:1] in "{d" and len(key) > 1 and key[1] in staffs:
                sold.append((key, staffs[key[1]]))
            if key[:1] == "p":
                bought.append(key)
            if key:
                policy.confirm_key_posted(key)
        record = sequence.state(policy)
        self.assertEqual(record.absorbed, {sequence.SV_STAFF_IDENTIFY: 21,
                                           sequence.SV_STAFF_DETECT_GOLD: 19})
        self.assertEqual(record.stage, 2)
        self.assertEqual((sold, bought), ([], []))
        self.assertEqual(policy.last_reason, "me-staff:travel-morivant", key)
        self.post(policy, staff_board(10), key)

    def test_unread_list_keeps_every_sequence_staff(self):
        # In the shop before any read: no sequence staff is a sale or a buy.
        policy = staff_policy(staff_board(1), record=False)
        board = parse_snapshot(staff_board(1), policy._monrace_knowledge)
        carried = [item for item in board.inventory if item.tval == 55]
        self.assertEqual(len(carried), 4)
        self.assertTrue(all(sequence.retains(policy, board, item) for item in carried))
        shelf = [item for item in board.store.items if item.tval == 55
                 and item.sval == sequence.SV_STAFF_IDENTIFY]
        self.assertTrue(shelf and all(sequence.purchase_excluded(policy, board, item)
                                      for item in shelf))
        self.assertIsNone(sequence.purchase(policy, board))


class HomeEquipmentSessionTest(PostedKey):
    """鍵1c: the staff sequence took the board from a Home equipment session.

    life-054 072115: the optimizer's 24-action Home transaction (context home)
    refused every other shop's route, and the sequence's Magic-shop approach
    waited for it: 82 x shop:approach '5', then no-progress:buy.
    DECLARED RECONSTRUCTED: the captures omit session objects; the session is
    the decision row's next action (deposit of the pack item it names), as in
    test_lv7_town_stop_recorded.  The sequence record is RECORDED_SEQUENCE in
    stage 2 with the stage-2 staffs not yet bought (the 07:18 restart).
    """

    def boundary(self):
        from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
        from hengbot.equipment_transaction_planner import (
            EquipmentTransaction, EquipmentTransactionPlan,
        )
        from hengbot.equipment_transaction_session import EquipmentTransactionSession
        raw = copy.deepcopy(CASE["equipment"]["board"])
        policy = staff_policy(raw, bought=[5, 10], fundraise_runs=0, reached_runs=0,
                              fundraise_why=None)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        action = CASE["equipment"]["decision"]["equipment_optimization"]["transaction_next"]
        item = next(it for it in board.inventory
                    if equipment_identity(it) == action["item_id"].split(":")[1])
        transaction = EquipmentTransaction(**action, item_identity=equipment_identity(item),
                                           move_identity=equipment_move_identity(item))
        policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((transaction,), (), len(raw["inventory"])))
        return policy, raw

    def test_capture_pins_the_home_session_and_the_waiting_approach(self):
        row = CASE["equipment"]["decision"]
        self.assertEqual((row["reason"], row["key"]), ("shop:approach", "5"))
        self.assertEqual(row["equipment_optimization"]["transaction_context"], "home")
        self.assertEqual(row["equipment_optimization"]["transaction_actions"], 24)
        self.assertEqual(CASE["equipment"]["stop"]["reason"], "quest:blocked:me-staff")

    def test_staff_sequence_yields_to_the_home_session(self):
        policy, raw = self.boundary()
        key = decide(policy, raw)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(sequence._phase(policy, board), "buy")
        self.assertEqual(policy.last_reason, "equipment-transaction:travel-home", key)
        self.post(policy, raw, key)


class Q1TorchForceTest(PostedKey):
    """鍵2: Q1's Magic-Eater gate measured melee (life-058 084721, Lv7, 223 gold).

    Melee 3.08 < 3.6 failed both tiers, so the route asked two Healing and one
    Speed potion (7,450 gold with the torch) and stopped unaffordable.  The
    owner's plan (2026-10-30 「松明を購入して松明で戦う。魔法は補助。」) fights
    with thrown torches: the force is their output, and the one missing torch
    (3 gold) is bought.  The opening policy is new on ring row 207 and is
    driven over the recorded boards 207-222 (Home and ~f rows from the ring).
    """

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()

    def drive(self):
        # The production policy of the recorded opening-route tests (town map,
        # quest knowledge and strategies), primed on this capture's boards.
        opening = CASE["opening"]
        boards = opening["boards"]
        policy, _ = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces=CASE["monraces"], snapshot=boards[0],
            knowledge=[opening["skill"], opening["home"]], state={"modes_and_latches": {}}))
        for raw in boards:
            key = decide(policy, raw, opening["skill"])
        return policy, boards[-1], key

    def test_capture_pins_the_melee_gate(self):
        readiness = CASE["opening"]["stop"]["fixedquest_readiness"]
        self.assertEqual(readiness["strategy_force"]["dps"], {"measured": 3.08, "required": 3.6})
        self.assertEqual(readiness["strategy_force"]["lit_torch"], {"measured": 19, "required": 20})
        player = CASE["opening"]["boards"][-1]["player"]
        self.assertEqual((player["class_id"], player["level"], player["max_hp"], player["gold"]),
                         (16, 7, 116, 223))

    def test_torch_output_is_the_force_and_the_missing_torch_is_bought(self):
        from hengbot.model import STORE_GENERAL
        policy, raw, key = self.drive()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None), policy.last_reason)
        self.assertNotEqual(key, "")
        self.assertEqual([row[1:3] for row in policy._opening_q1_requirements(board)],
                         [(20, 19), (0, 0), (0, 0)])
        self.assertEqual(policy._opening_q1_plan(board)[:2], ("quest-throwing-items", STORE_GENERAL))
        force = policy.fixed_quest_readiness_state()["strategy_force"]
        self.assertEqual((force["dps"]["measured"], force["melee_dps"]), (16.76, 3.08))
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
