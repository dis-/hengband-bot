"""The Zul trip's walk over the mountains is its own progress (n1-b life-397 2026-11-14 17:18).

n1-b life-397 (Magic-Eater Lv46, build d7356e57ae) claimed Q25 at the Outpost, walked the
global map to Zul for its mutations (zul_trip) and arrived at (64,1), on Zul's mountains.
The Zul trip's step toward the Chaos Tower ('9', town:zul:approach-tower, its Reach the
Tower declared under cross-town) reached the progress seam (_town_procurement_decision).
``_town_result_makes_progress`` honoured a declared cross-town Reach only for reasons that
start with ``town:cross-town``; for town:zul: it judged the step against no goal, called
it no progress and handed the visit over to the Alchemist walk of the recall and CCW
shortage (town-progress-invariant:defect:town:zul:approach-tower=>...approach,
'\\x1b`n%.').  The game's travel has no route over the mountains, the entry was
interrupted, the replan had no key and the bot stopped no-key-exhausted.

Fix: the declared Reach judges every reason the arbiter files under cross-town
(town_arbiter: town:cross-town, town:morivant, town:arena:, town:zul:,
town:wand-recharge:).

Recorded: the capture's town-arrival checkpoint and its 64 journal rows, then the snapshot
ring's 22 player-turn boards that follow (the global-map walk and the Zul arrival board),
tests/extract_n1b_397_zul_arrival_1114_fixture.py, through the public choose_key with the
recorded keys acknowledged; the arrival's key is posted through the production executor
(``_ExecutorInputPort``).  Row 0 is FORCED (the periodic character dump's timer runs on the
replay's clock).  The recorded arrival decision was periodic:skill-exp-knowledge on the
live clock; the replay's clock asks no skill list there, so the arrival board's first
decision is the Zul trip's own.

DECLARED CONSTRUCTED: the boards after the arrival (each step moves the player one cell,
ten game turns on).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.town_visit_plan import PROGRESS_INVARIANT_PREFIX
from support.town_arrival_fixture import load
from tests.support import recorded as harness

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-397-zul-arrival-1114"
FORCED = {0}
DIRECTIONS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
              "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
APPROACH = "town:zul:approach-tower"


class N1b397ZulArrival1114RecordedTest(harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        ring = json.loads(lzma.decompress((FIXTURE / "ring-boards.json.xz").read_bytes()))
        cls.ring_boards, cls.ring_decisions = ring["boards"], ring["decisions"]
        cls.skill_exp = ring["skill_exp"]

    def load(self):
        scratch = self.scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, self.journal, rows = load(FIXTURE, Path(scratch.name))
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        return policy, rows

    def to_zul_arrival(self):
        """The journal and the global-map walk decided as recorded; the Zul arrival's raw board."""
        policy, rows = self.load()
        for recorded, supply in rows:
            key = policy.choose_key(supply())
            if recorded["row"] not in FORCED:
                self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])
            policy.confirm_key_posted(recorded["key"])
        self.assertEqual((rows[-1][0]["key"], rows[-1][0]["reason"]), ("<", "town:zul:enter-global"))
        for raw, (key, reason, turn) in zip(self.ring_boards[:-1], self.ring_decisions[:-1]):
            self.assertEqual(raw["turn"], turn)
            decided = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            self.assertEqual((decided, policy.last_reason), (key, reason), turn)
            policy.confirm_key_posted(key)
        self.assertEqual(self.ring_decisions[-2][:2], [">", "town:zul:enter-town"])
        return policy, copy.deepcopy(self.ring_boards[-1])

    def test_the_arrival_is_zul_with_an_alchemist_shortage(self):
        policy, raw = self.to_zul_arrival()
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual((board.town_id, board.player.position.y, board.player.position.x), (4, 64, 1))
        self.assertIsNotNone(policy._zul_trip)
        # The recorded stop: the arrival's trip step was replaced by the Alchemist walk.
        self.assertEqual(self.ring_decisions[-1][:2], ["~f\x1b", "periodic:skill-exp-knowledge"])

    def test_the_walk_over_the_mountains_keeps_its_steps(self):
        policy, raw = self.to_zul_arrival()
        tower = None
        steps = []
        walked = 0
        for _ in range(10):
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = policy.choose_key(board)
            steps.append((key, policy.last_reason))
            self.assertIsNotNone(key, steps)
            self.assertFalse(policy.last_reason.startswith(PROGRESS_INVARIANT_PREFIX), steps)
            if policy.last_reason.startswith("periodic:"):
                # The periodic skill-list request (the recorded arrival's first decision) is an
                # interrupt, answered with the recorded reply (ring row 2140); the board is the
                # same one (DECLARED CONSTRUCTED: no turn passes).
                self.assertEqual(key, "~f\x1b", steps)
                policy.confirm_key_posted(key)
                _consume_response_sequence(
                    [json.dumps(self.skill_exp, ensure_ascii=False) + "\n"], policy,
                    lambda _key: True, policy._monrace_knowledge, parse_snapshots=False,
                    knowledge_ledger_path=Path(self.scratch.name) / "knowledge.jsonl")
                continue
            self.assertEqual(policy.last_reason, APPROACH, steps)
            self.assertIn(key, DIRECTIONS, steps)
            slot = policy._decision_goal
            self.assertEqual((slot[0], slot[1].kind), ("cross-town", "Reach"))
            tower = tower or slot[1].cell
            self.assertEqual(slot[1].cell, tower)
            dy, dx = DIRECTIONS[key]
            following = self.later(raw)
            following["player"] = dict(following["player"], y=raw["player"]["y"] + dy,
                                       x=raw["player"]["x"] + dx)
            before = max(abs(raw["player"]["y"] - tower[0]), abs(raw["player"]["x"] - tower[1]))
            after = max(abs(following["player"]["y"] - tower[0]),
                        abs(following["player"]["x"] - tower[1]))
            self.assertLess(after, before, steps)
            self.assertEqual(self.post(policy, raw, key, [], following), [key])
            policy.confirm_key_posted(key)
            raw = following
            walked += 1
        self.assertGreaterEqual(walked, 6, steps)


if __name__ == "__main__":
    unittest.main()
