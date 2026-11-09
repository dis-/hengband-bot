"""The dungeon and Home stops of 2026-11-04 on build bot-014ddb7dd, one per root.

Recorded: tests/extract_open_stops_1104_fixtures.py.  Boards decide through the
public chooser; the Home stop replays its arrival checkpoint and posts the fixed
decision through the production executor port.  The skill-exp cache of a board
whose ring holds no skill row is DECLARED CONSTRUCTED from the board's level.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests.support.recorded import EDIT, _policy
from tests.support import recorded as executor_pins
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures") / "open-stops-1104"
APPROACH = "immobile-threat:approach-to-shoot"


class DungeonBoards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURES / "boards.json.gz", "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def primed(self, raw):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.monrace))
        policy._skill_exp_cache = (0, 0, raw["player"]["level"], None)
        return policy

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return key, policy.last_reason

    def test_a_walk_to_shoot_does_not_step_again_from_a_cell_it_came_back_to(self):
        """life-477 08:53 (telepathy lifts ``unaimed``, seek-downstairs walks back) and
        life-308 12:42 (a dark corpse heap is seen only from beside it, the next
        heap's walk leads back): both alternated to the loop guard."""
        boards = self.case["esp_walk"]
        policy = self.primed(boards[0])
        self.assertEqual(self.decide(policy, boards[0]), ("4", APPROACH))
        self.assertEqual(self.decide(policy, boards[1]), ("6", "seek-downstairs"))
        # Recorded: ('4', APPROACH).
        self.assertEqual(self.decide(policy, boards[2]), ("6", "seek-downstairs"))

        boards = self.case["dark_walk"]
        policy = self.primed(boards[0])
        for raw in boards[:-3]:
            self.decide(policy, raw)
        self.assertEqual(self.decide(policy, boards[-3]), ("3", APPROACH))
        self.decide(policy, boards[-2])
        # Recorded: ('3', APPROACH) at (25,74).
        key, reason = self.decide(policy, boards[-1])
        self.assertNotEqual(reason, APPROACH)
        self.assertNotEqual(key, "3")

    def test_no_blow_is_struck_at_a_jelly_the_worn_zantetsu_cannot_cut(self):
        """life-307 11:21 and 11:23: Zantetsu on a small aqua illusion ('j'), every blow
        cut to zero (player-attack.cpp:545), stall:melee twice."""
        raw = self.case["zantetsu"]
        policy = self.primed(raw)
        key, reason = self.decide(policy, raw)
        # Recorded: ('4', 'melee').
        self.assertNotEqual(reason, "melee")
        self.assertNotEqual(key, "4")

    def test_the_frontier_walk_commits_no_route_over_damaging_ground(self):
        """life-478 10:45, dead on deep acid: the oscillation's global frontier route
        (601910, breakout:seek-frontier) crossed it past hazard-free frontiers.  The
        floor memory, visits and written-off frontiers are the policy's own at the
        death, 90 decisions on (policy-state.json): DECLARED CONSTRUCTED for this board."""
        raw = self.case["acid"]
        policy = self.primed(raw)
        memory = self.case["acid_memory"]
        for name, cells in memory["terrain"].items():
            getattr(policy, f"_remembered_{name}").update(map(tuple, cells))
        policy._visit_counts.update(
            {Position(*entry["key"]): entry["count"] for entry in memory["visits"]})
        policy._probed_frontiers.update(Position(*cell) for cell in memory["probed"])
        for _ in range(40):
            self.decide(policy, raw)
            if policy.last_reason == "breakout:seek-frontier":
                break
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        self.assertEqual(policy.last_reason, "breakout:seek-frontier")
        self.assertEqual([step for step in policy._explore_path
                          if policy._is_damaging_grid(board.grids.get(step))], [])


class HomeTake(executor_pins.ProductionHarness):
    def test_a_take_merged_into_a_carried_stack_moves_the_next_address(self):
        """life-308 12:23: the Identify staff merged into the carried one under a new
        name, so the take read as failed, the catalogue stayed valid and the next
        take asked for 'H' on a shelf now ending at 'G' (stuck-prompt)."""
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        visit = root / "town-arrival"
        visit.mkdir()
        fixture = FIXTURES / "home-take"
        (visit / POLICY_FILE).write_bytes(lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        policy = restore(visit, root)
        adopt_calibration(policy, fixture / "calibration.json", root)
        Path(policy._home_disposal.history_path).unlink(missing_ok=True)
        recorded, steps = journal(visit), list(decisions(policy, visit, root))
        self.assertIn("pH18", recorded[-1]["key"])
        result = replay_window("home-take", policy, iter(steps[:-1]))
        self.assertIsNone(result.first_divergence)

        board = steps[-1][1]()
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5", "home:atomic-deposit"))
        raw_board = json.loads(recorded[-1]["line"] or recorded[-1]["inputs"][-1])
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


if __name__ == "__main__":
    unittest.main()
