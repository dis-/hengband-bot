"""The town stops of the viewing bots, 2026-11-05 and 06.

Recorded: each case's arrival checkpoint, sidecars and visit journal
(tests/extract_town_stops_1105_fixtures.py).  The rows before the fixed decision
replay unchanged through the public chooser and the driver's retirement entrance;
the fixed decision is posted through the production executor port.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import os
from pathlib import Path
import re
import tarfile
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest

from hengbot import cli
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import SIDECAR_DIRECTORY
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests import test_input_executor as executor_pins


FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1105"
DUMP_KEY = "Cf"
BURST = "town:blocked:owner-retired-burst"


class TownStops1105RecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, case):
        visit = self.scratch / case / "town-arrival"
        visit.mkdir(parents=True)
        with tarfile.open(FIXTURES / f"{case}.tar.xz") as tar:
            tar.extractall(visit, filter="data")
        runtime = self.scratch / case / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        if calibration.is_file():
            adopt_calibration(policy, calibration, runtime)
        self.visit = visit
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def decide(self, policy, supply):
        """As the driver: the chooser, then the retirement entrance."""
        board = supply()
        before = copy.copy(policy._store_visit)
        chosen = policy.choose_key(board)
        reason = policy.last_reason
        key = policy.validate_read_key(board, chosen)
        args = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
        return board, chosen, reason, cli._handle_owner_retirement(args, board, key, policy, before)

    def post(self, policy, key):
        if key.startswith(DUMP_KEY) and policy._character_dump_path is not None:
            # DECLARED CONSTRUCTED: the game writes the sheet; the arrival's sheet
            # stands for it.
            dump = Path(policy._character_dump_path)
            recorded = self.visit / SIDECAR_DIRECTORY / "_character_dump_path"
            dump.write_bytes(recorded.read_bytes() if recorded.is_file() else b"")
            os.utime(dump, ns=(time.time_ns(), time.time_ns()))
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay_to(self, policy, recorded, steps, row):
        """Replay the rows before ``row`` unchanged; decide ``row``."""
        for index in range(row):
            _, chosen, reason, key = self.decide(policy, steps[index][1])
            self.assertEqual((chosen, reason), (recorded[index]["key"], recorded[index]["reason"]),
                             f"row {index}")
            self.assertNotEqual(policy.last_reason, BURST, f"row {index}")
            self.post(policy, key)
        return self.decide(policy, steps[row][1])

    def assert_posts(self, policy, row, board, key):
        raw_board = json.loads(row["line"] or row["inputs"][-1])
        game = executor_pins.FaithfulHookGame()
        game.state = raw_board
        game.screen = executor_pins.command_screen(raw_board["turn"])
        # DECLARED CONSTRUCTED: the next board after the command.
        game.screens = [executor_pins.command_screen(raw_board["turn"] + 10)]
        game.states = [dict(raw_board, turn=raw_board["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)

    def test_a_plain_walk_earns_its_distance_credit(self):
        """n1-b life-314 13:43: town:rumor walked 11 steps to the inn.
        me_powers.fight_key, the pass-through of every decision, took the work record,
        so no walk or effect earned credit: the burst at the third retirement."""
        policy, recorded, steps = self.load("rumor-walk")
        board, _, _, key = self.replay_to(policy, recorded, steps, 11)
        self.assertEqual((key, policy.last_reason), ("1", "town:rumor"))
        self.assertLess(policy._owner_retired_no_progress_count, 3)
        self.assert_posts(policy, recorded[11], board, key)

    def test_a_relief_of_another_town_waits_for_the_trip(self):
        """n1-c life-145 23:18: relief of the Outpost, recharge at Morivant's tower;
        town:blocked:home-full-town-changed x9, then the burst."""
        policy, recorded, steps = self.load("town-changed")
        self.assertEqual(recorded[6]["reason"], "town:blocked:home-full-town-changed")
        board, _, _, key = self.replay_to(policy, recorded, steps, 6)
        self.assertEqual((key, policy.last_reason), ("9", "me-staff:return-outpost"))
        self.assert_posts(policy, recorded[6], board, key)

    def test_a_home_walk_keeps_its_way_past_the_plan(self):
        """n1-b life-317 23:19 (Lv34, retired): the relief's walk to Home and the
        plan's Alchemist alternate at (34,90) and (33,91): transfer [4, 7]."""
        policy, recorded, steps = self.load("own-home-route")
        self.assertEqual(recorded[71]["key"], "1")
        board, _, _, key = self.replay_to(policy, recorded, steps, 71)
        self.assertEqual((key, policy.last_reason), ("9", "shop:approach"))
        self.assertEqual(policy._store_visit.store_type, 7)
        self.assert_posts(policy, recorded[71], board, key)

    def test_the_identify_swap_takes_the_whole_emptiest_stack(self):
        """n1-a life-487 19:14: 7, 6 and 2x3 charges, 4x18 at 816 gold on the shelf,
        726,000 gold and the pack at its budget: the swap released nothing and the
        visit stopped at survival:identify_staff_ready with 19 of 20."""
        policy, recorded, steps = self.load("staff-swap")
        board, _, _, key = self.replay_to(policy, recorded, steps, 15)
        self.assertEqual((key, policy.last_reason), ("d02\ry", "shop:in-store-sell"))
        self.assertFalse(policy._identify_staff_acquisition_worthwhile(board, 3))
        self.assertTrue(policy._identify_staff_acquisition_worthwhile(board, 18))
        self.post(policy, key)
        # DECLARED CONSTRUCTED: the shop's answers to the sales that follow.
        raw = json.loads(recorded[15]["line"] or recorded[15]["inputs"][-1])
        raw["inventory"] = [item for item in raw["inventory"]
                            if not (item["tval"] == 55 and item["sval"] == 5 and item["charges"] == 3)]
        raw["player"]["gold"] += 100
        for _ in range(4):
            raw = copy.deepcopy(raw)
            raw["turn"] += 1
            for index, item in enumerate(raw["inventory"]):
                item["slot"] = chr(ord("a") + index)
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            policy.observe_store_screen(True)
            key = policy.choose_key(board)
            if key.startswith("p"):
                break
            policy.confirm_key_posted(key)
            inscribed = re.match(r"\{([a-z])@(\d)\r", key)
            if inscribed:
                for item in raw["inventory"]:
                    if item["slot"] == inscribed.group(1):
                        item["inscription"] = "@" + inscribed.group(2)
                        item["name"] += " {@" + inscribed.group(2) + "}"
            sold = re.match(r"d(\d)y", key)
            if sold:
                raw["inventory"] = [item for item in raw["inventory"]
                                    if "@" + sold.group(1) not in item["name"]]
                raw["player"]["gold"] += 100
        self.assertEqual(policy.last_reason, "shop:in-store-buy")
        shelf = raw["store"]["items"]
        offset = ord(key[1]) - ord("a")
        bought = next((item for item in shelf if item.get("slot") == key[1]), shelf[offset])
        self.assertEqual((bought["tval"], bought["sval"], bought["charges"]), (55, 5, 18))

    def test_a_refused_deposit_leaves_the_filed_take_its_way_home(self):
        """n1-a life-487 19:30: the deposit a full Home refused closed Home on the pass
        the take was filed for; town:blocked:unmet:home_candidate_resolved."""
        policy, recorded, steps = self.load("filed-take")
        self.assertEqual(recorded[57]["reason"], "town:blocked:unmet:home_candidate_resolved")
        board, _, _, key = self.replay_to(policy, recorded, steps, 57)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assert_posts(policy, recorded[57], board, key)

    def test_the_departure_walks_on_after_a_hit_on_its_way(self):
        """n1-a life-487 13:39: one melee from the entrance on the way to a mining run,
        the hold kept the departure out of its own route:
        town:blocked:survival:cure_critical_ready."""
        policy, recorded, steps = self.load("entrance-walk")
        self.assertEqual(recorded[61]["reason"], "town:blocked:survival:cure_critical_ready")
        board, _, _, key = self.replay_to(policy, recorded, steps, 61)
        self.assertEqual((key, policy.last_reason), ("9", "seek-downstairs"))
        self.assert_posts(policy, recorded[61], board, key)

    def test_the_quest_return_leaves_the_expedition_at_morivant(self):
        """n1-a life-486 11:41: travel-2 and fixedquest:prepare-return alternate, 500
        gold a leg, 5,061 gold to 61."""
        policy, recorded, steps = self.load("expedition")
        self.assertEqual(recorded[55]["reason"], "fixedquest:prepare-return")
        board, _, _, key = self.replay_to(policy, recorded, steps, 55)
        self.assertFalse(policy.last_reason.startswith("fixedquest:"))
        self.assertIsNotNone(policy._morivant_full_identify)
        self.assert_posts(policy, recorded[55], board, key)


if __name__ == "__main__":
    unittest.main()
