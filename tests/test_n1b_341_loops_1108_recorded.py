"""n1b-341-loops-1108: the three loop stops of n1-b life-341 (Lv34 Magic-Eater), 2026-11-08.

Fixture: tests/fixtures/n1b-341-loops-20261108.json.gz
(tests/extract_n1b_341_loops_1108_fixture.py).  Every decision is the public
``choose_key``; the asserted keys go through the production executor.

- 0400 (dungeon 12, 49F) and 0418 (Angband 49F): a strong sleeper (巨大首なし race 653 at
  [28,35]; 混沌の落とし子 race 574 at [34,7]) is retreated from even asleep (owner 2026-11-07
  「眠っている敵でも強い敵からは離れる」), but where no step is farther from it the retreat
  gives the board up, and the explore stepped one cell nearer ('8' from [36,36], '2'/'3' from
  [29,9]/[29,8]), the retreat stepped back, forty times until the loop detector.  Now the
  cells nearer a sleeper than the player are the routes' veto inside its area
  (``_engagement_danger_cells``), and the explore planner honours that set.
- 0420 (Angband 49F, the restarted process): three sleeping 青オクタロック (race 1411) 18-20
  cells away were a material threat to the loot (``_loot_block_reason``) at [38,75] and out
  of sight one step away, so seek-loot and explore took turns.  The block is now remembered
  with its sleepers while they are out of sight (sleeper_loot_block).

DECLARED RECONSTRUCTION: 0400 replays its capture from the first board with a fresh policy,
as recorded through the stop.  0418 starts from the capture's first board with a fresh
policy given the stop's retreat vetoes and deferred loot (its policy-state.json), which the
live process had set before the capture began.  0420 restores a checkpoint of a fresh policy
that replayed the restarted process's snapshot lines (fixture tool's docstring) up to the
board of turn 2480700; its decisions from there match the recorded rows on main.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import copy
import gzip
import json
import os
from pathlib import Path
from unittest import mock

from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HUNT_RANGE
from tests.support import recorded as executor_pins
from tests.test_dungeon_1031_recorded import READ_PROMPT, RecordedHarness, decide
from tests.test_town_decision_speed_caches import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-341-loops-20261108.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    DATA = json.load(_stream)
CASES = DATA["cases"]
AVOID = "threat:avoid-engagement"
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
SLEEPERS = {"0400": Position(28, 35), "0418": Position(34, 7)}
OCTOROK = 1411


def knowledge():
    races = {}
    for race, facts in DATA["monraces"].items():
        facts = copy.deepcopy(facts)
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
        facts["names"] = tuple(facts["names"])
        races[int(race)] = MonraceKnowledge(**facts)
    return races


def recorded(name):
    return {row["turn"]: (row["key"], row["reason"]) for row in CASES[name]["decisions"]}


def here(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


def fresh(name):
    """A fresh policy on the case's first board (0418: with the stop's vetoes and loot)."""
    case = CASES[name]
    policy = HengbotPolicy(monrace_knowledge=knowledge())
    first = parse_snapshot(copy.deepcopy(case["boards"][0]), policy._monrace_knowledge)
    policy.prime(first)
    if "deferred_loot" in case:
        loot = {Position(*cell) for cell in case["deferred_loot"]}
        policy._deferred_loot |= loot
        policy._nav_ledger_deferred_loot |= loot
        policy._claim_engagement_avoid_cells(
            [Position(*cell) for cell in case["avoid_cells"]],
            snapshot=first, threats=first.visible_monsters)
    return policy


def restored_0420():
    with mock.patch.dict(os.environ, {
            "HENGBAND_MONRACE_DEFINITIONS": str(EDIT / "MonraceDefinitions.jsonc")}):
        return restore_checkpoint_bytes(
            HengbotPolicy, base64.b64decode(CASES["0420"]["checkpoint"]))


class StrongSleeperReachRecordedTest(RecordedHarness):
    def test_recorded_rows_step_nearer(self):
        for name, turn, cell, key in (("0400", 2377055, (36, 36), "8"),
                                      ("0418", 2472011, (29, 9), "2")):
            raw = next(board for board in CASES[name]["boards"] if board["turn"] == turn)
            self.assertEqual(here(raw), Position(*cell))
            self.assertEqual(recorded(name)[turn], (key, "explore"))
            sleeper = SLEEPERS[name]
            step = Position(cell[0] + MOVES[key][0], cell[1] + MOVES[key][1])
            self.assertLess(step.distance_to(sleeper), here(raw).distance_to(sleeper))
            self.assertLessEqual(here(raw).distance_to(sleeper), HUNT_RANGE)
            self.assertTrue(raw["visible_monsters"][0]["asleep"])

    def assert_no_step_nearer(self, name):
        """Every recorded board: no decided step but the retreat's goes nearer the sleeper."""
        policy = fresh(name)
        sleeper = SLEEPERS[name]
        decided = []
        for raw in CASES[name]["boards"]:
            key = decide(policy, copy.deepcopy(raw))
            if key:
                policy.confirm_key_posted(key)
            decided.append((raw, key, policy.last_reason))
            if key not in MOVES or not raw["visible_monsters"]:
                continue
            start = here(raw)
            if start.distance_to(sleeper) > HUNT_RANGE:
                continue
            step = Position(start.y + MOVES[key][0], start.x + MOVES[key][1])
            self.assertGreaterEqual(step.distance_to(sleeper), start.distance_to(sleeper),
                                    (raw["turn"], key, policy.last_reason))
        return decided

    def test_0400_explore_keeps_out_of_the_sleepers_reach(self):
        decided = self.assert_no_step_nearer("0400")
        raw, key, reason = next(row for row in decided if row[0]["turn"] == 2377055)
        self.assertNotEqual((key, reason), ("8", "explore"))

    def test_0418_explore_keeps_out_then_the_vetoes_enclosure_leaves(self):
        decided = self.assert_no_step_nearer("0418")
        # The retreats' own vetoes close the pocket the sleeper's reach leaves: the
        # existing enclosed-floor answer leaves the floor.
        raw, key, reason = next(row for row in decided if row[2] == "stuck:recall-escape")
        board = parse_snapshot(copy.deepcopy(raw), knowledge())
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot)
        policy = fresh("0418")
        self.assertEqual(self.post(policy, raw, key, [executor_pins.prompt_screen(READ_PROMPT)],
                                   self.later(raw)), ["r", recall.slot])

    def test_0400_first_kept_out_key_through_the_executor(self):
        policy = fresh("0400")
        for raw in CASES["0400"]["boards"]:
            key = decide(policy, copy.deepcopy(raw))
            if raw["turn"] == 2377055:
                break
            if key:
                policy.confirm_key_posted(key)
        self.assertEqual(here(raw), Position(36, 36))
        self.assertNotIn(key, MOVES)
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), [key])


class SleeperLootBlockRecordedTest(RecordedHarness):
    def test_recorded_rows_alternate(self):
        boards, rows = CASES["0420"]["boards"], recorded("0420")
        self.assertEqual((here(boards[0]), rows[boards[0]["turn"]]), (Position(38, 75), ("1", "explore")))
        self.assertEqual({row["race_id"] for row in boards[0]["visible_monsters"]}, {OCTOROK})
        self.assertTrue(all(row["asleep"] for row in boards[0]["visible_monsters"]))
        self.assertEqual((here(boards[1]), rows[boards[1]["turn"]]), (Position(39, 74), ("9", "seek-loot")))
        self.assertEqual(boards[1]["visible_monsters"], [])

    def test_out_of_their_sight_the_loot_stays_blocked(self):
        policy = restored_0420()
        boards = CASES["0420"]["boards"]
        out_of_sight = 0
        for index, raw in enumerate(boards):
            key = decide(policy, copy.deepcopy(raw))
            if index == 1:
                self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), [key])
            if key:
                policy.confirm_key_posted(key)
            if not raw["visible_monsters"]:
                out_of_sight += 1
                self.assertNotEqual(policy.last_reason, "seek-loot", (raw["turn"], key))
                board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
                self.assertEqual(policy._loot_block_reason(
                    policy._with_grid_memory(board), []), "material-threat")
        self.assertGreater(out_of_sight, 10)


if __name__ == "__main__":
    import unittest
    unittest.main()
