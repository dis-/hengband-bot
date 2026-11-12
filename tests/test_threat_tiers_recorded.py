"""Threat tiers, plan step 1 (docs/threat-tiers-design.md): recorded boards, and no decision changes.

Step 1 only observes: ``threat_tiers.facts`` is written to the decision row next to
``threat_prediction`` (cli ``_capture_decision_facts``, inside the observer scope).  The recorded
boards below are labelled as the design says; the replays show that capturing the facts after
every decision leaves every decided key and reason as it was.

Fixtures (all existing):
- death-n1a-475-1104 (n1-a life-475, Lv~40 warrior among undead and summoners): T1.
- q25-mass-n1c-159-1107 (Quest 25, n1-c life-159): sequence 274, T2 by the Speed dose alone
  (D7 「加速を先に」); the recorded answer there was quest-strategy:hold, then the plan's own Speed.
- death-n1a-450-1101 (n1-a life-450, the speed +10 ランゴスタ two cells away): T3 on the recall
  wait, 即死 by the paralyser in contact on the death board.
- death-n1c-123-1104 (n1-c life-123, hallucinated at HP 49/487): 即死 by the hallucination rule.
- n1b-325-low-hp-escape-1106 (n1-b life-325, Castle 33F): the hasted jackals and 智天使 are
  weighed at speed + 10.
DECLARED CONSTRUCTED where a test edits a recorded board (the hasted-monster case), as it says.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle
from hengbot import threat_tiers
from hengbot.cli import _capture_decision_facts, _PolicyObserverScope, _write_decision
from hengbot.model import parse_snapshot
from tests import test_n1c_deaths_1101_recorded as d57
from tests import test_q25_n1c_159_1107_recorded as q25

FIXTURES = Path(__file__).with_name("fixtures")


def load(name):
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as stream:
        return json.load(stream)


CASES = {name: load(name) for name in (
    "death-n1a-475-1104.json.gz", "death-n1a-450-1101.json.gz", "death-n1c-123-1104.json.gz",
    "n1b-325-low-hp-escape-1106.json.gz", "town-end-purchase-only-1102.json.gz",
    "summon-response-n1a-475-1104.json.gz", "death-n1c-099-1102.json.gz")}


def boards(case):
    return [raw for raw in case["boards"] if isinstance(raw, dict)
            and raw.get("type", "state") != "knowledge" and "player" in raw]


def replay_to(name, turn):
    """(policy, board) on the recorded ``turn``: one policy decides the boards before it in order."""
    case = CASES[name]
    raws = boards(case)
    policy = d57.loops.new_policy(dict(case, boards=raws), case["skill"], monraces=case.get("monraces"))
    for raw in raws:
        key = d57.loops.decide(policy, raw)
        if raw["turn"] == turn:
            return policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        if key:
            policy.confirm_key_posted(key)
    raise AssertionError(turn)


def assess(policy, board):
    with _PolicyObserverScope(policy):
        return threat_tiers.assess(policy, board)


class RecordedTiersTest(unittest.TestCase):
    def test_t1_n1a_475_undead_and_summoners(self):
        policy, board = replay_to("death-n1a-475-1104.json.gz", 2039000)
        result = assess(policy, board)
        self.assertEqual(result.tier, threat_tiers.T1)
        self.assertIsNone(result.supply_plan)
        self.assertFalse(result.instant_death)
        # The 22-turn free horizon is past the cost cap: its bracket's low end already exceeds HP.
        self.assertIsNone(result.free_incoming)
        low, high = result.free_incoming_bounds
        self.assertGreater(low, board.player.hp)
        self.assertGreaterEqual(high, low)
        self.assertTrue(any(row.worsens_with_time for row in result.per_monster.values()))

    def _q25_274(self):
        policy = q25.new_policy(q25.CASE["boards"][0])
        for raw, row in zip(q25.CASE["boards"], q25.CASE["recorded"]):
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            if row["sequence"] == 274:
                break
            policy.confirm_key_posted(str(policy.choose_key(board)))
        return policy, board

    def test_q25_blind_casters_keep_it_t1(self):
        """Owner 2026-11-11 「恐怖・盲目の呪文を持つ相手で耐性が無い時は T2 にしない」: race 748
        (SCARE, BLIND) and race 508 (BLIND) are in the engagement and n1-c life-159 has rFear
        but no rBlind: the Speed plan still wins on HP (margin kept), the tier is T1."""
        policy, board = self._q25_274()
        result = assess(policy, board)
        self.assertEqual((result.tier, result.t2_withheld), (threat_tiers.T1, ("blind-spell",)))
        self.assertIsNone(result.supply_plan)
        self.assertGreater(result.supply_margin, 0)

    def test_t2_q25_speed_first(self):
        """DECLARED CONSTRUCTED: rBlind added to the board (see the test above)."""
        policy, board = self._q25_274()
        board = replace(board, player=replace(
            board.player, abilities=board.player.abilities | {"resist_blind"}))
        result = assess(policy, board)
        self.assertEqual(result.tier, threat_tiers.T2)
        self.assertEqual(result.supply_plan.categories, ("speed",))
        self.assertGreater(result.supply_plan.speed_doses, 0)
        self.assertEqual(result.supply_plan.heals, ())
        self.assertGreaterEqual(result.free_incoming, board.player.hp)

    def test_t3_and_the_paralyser_n1a_450(self):
        policy, board = replay_to("death-n1a-450-1101.json.gz", 1268495)
        result = assess(policy, board)
        self.assertEqual(result.tier, threat_tiers.T3)
        self.assertFalse(result.instant_death)
        policy, board = replay_to("death-n1a-450-1101.json.gz", 1268509)
        result = assess(policy, board)
        self.assertEqual(result.instant_death_reasons, ("paralyzer-contact",))

    def test_hallucination_n1c_123(self):
        policy, board = replay_to("death-n1c-123-1104.json.gz", 3934818)
        result = assess(policy, board)
        self.assertTrue(board.player.hallucinated)
        self.assertIn("hallucination", result.instant_death_reasons)

    def test_hasted_monsters_n1b_325(self):
        policy, board = replay_to("n1b-325-low-hp-escape-1106.json.gz", 2100397)
        result = assess(policy, board)
        jackals = [m for m in board.visible_monsters if m.race_id == 35]
        self.assertTrue(jackals and all(m.fast for m in jackals))
        for jackal in jackals:
            self.assertEqual(result.per_monster[jackal.index].speed, jackal.speed + 10)
        cherub = next(m for m in board.visible_monsters if m.race_id == 511)
        self.assertEqual(result.per_monster[cherub.index].worsens_with_time, ("summon",))

    def test_hasted_neighbours_raise_the_next_action_p95_n1a_475(self):
        # DECLARED CONSTRUCTED: the recorded board's adjacent hostiles are marked hasted.
        policy, board = replay_to("death-n1a-475-1104.json.gz", 2039000)
        calm = assess(policy, board)
        hasted = replace(board, visible_monsters=[
            replace(m, fast=True) if m.hostile and m.distance <= 1 else m
            for m in board.visible_monsters])
        result = assess(policy, hasted)
        self.assertGreater(result.next_action_p95, calm.next_action_p95)
        # The recorded observed loss (the unseen correction) counts on both boards.
        hp = calm.next_action_p95 + calm.unseen_correction + 1
        between = replace(hasted, player=replace(hasted.player, hp=hp))
        self.assertFalse(assess(policy, replace(board, player=between.player)).instant_death)
        self.assertTrue(assess(policy, between).instant_death)


class CostTest(unittest.TestCase):
    """The capture runs every decision: the slowest recorded boards stay cheap.

    Before the cost cap these took 811 ms (summon-response-n1a-475 at 2038858) and 207 ms
    (death-n1c-099 at 691696); with it about 10 and 25 ms.  The bound is generous for slow
    machines but far below the uncapped cost."""
    LIMIT_MS = 150

    def timed(self, policy, board):
        with _PolicyObserverScope(policy):
            started = time.perf_counter()
            facts = threat_tiers.facts(policy, board)
            return facts, (time.perf_counter() - started) * 1000

    def test_the_slowest_recorded_boards(self):
        for name, turn in (("summon-response-n1a-475-1104.json.gz", 2038858),
                           ("death-n1c-099-1102.json.gz", 691696)):
            with self.subTest(name=name):
                policy, board = replay_to(name, turn)
                facts, elapsed = self.timed(policy, board)
                self.assertEqual(facts["tier"], threat_tiers.T1)
                self.assertLess(elapsed, self.LIMIT_MS)

    def test_the_slowest_quest_25_board(self):
        policy = q25.new_policy(q25.CASE["boards"][0])
        for raw, row in zip(q25.CASE["boards"], q25.CASE["recorded"]):
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            if row["sequence"] == 275:
                break
            policy.confirm_key_posted(str(policy.choose_key(board)))
        facts, elapsed = self.timed(policy, board)
        self.assertEqual(facts["tier"], threat_tiers.T1)
        self.assertLess(elapsed, self.LIMIT_MS)


class DecisionRowTest(unittest.TestCase):
    def test_exp_to_advance_is_parsed(self):
        # bot-json-output.cpp:1621 exports it; the reward test (answer 5) reads it.
        raw = next(raw for raw in boards(CASES["death-n1a-475-1104.json.gz"])
                   if raw["turn"] == 2039000)
        policy, board = replay_to("death-n1a-475-1104.json.gz", 2039000)
        self.assertEqual(board.player.exp_to_advance, raw["player"]["exp_to_advance"])
        self.assertEqual(board.player.exp_to_advance, 1500000)
        raw = copy.deepcopy(raw)
        del raw["player"]["exp_to_advance"]
        self.assertIsNone(parse_snapshot(raw, policy._monrace_knowledge).player.exp_to_advance)

    def test_the_decision_row_carries_the_tiers_next_to_threat_prediction(self):
        policy, board = replay_to("death-n1a-450-1101.json.gz", 1268509)
        facts = _capture_decision_facts(board, policy)
        self.assertEqual(facts["threat_tiers"]["instant_death_reasons"], ["paralyzer-contact"])
        self.assertEqual(facts["threat_tiers"]["tier"], threat_tiers.T3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            _write_decision(path, board, "rd", "status-threat:scroll", policy, decision_facts=facts)
            record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertIn("threat_prediction", record)
        self.assertEqual(record["threat_tiers"]["instant_death"], True)


class DecisionInvarianceTest(unittest.TestCase):
    """Capturing the facts (threat tiers included) after every decision changes no decision."""

    def run_window(self, policy, raws, capture):
        rows, tiers = [], 0
        for raw in raws:
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = str(policy.choose_key(board))
            rows.append((raw.get("turn"), key, policy.last_reason))
            if capture:
                tiers += bool(_capture_decision_facts(board, policy).get("threat_tiers"))
            if key:
                policy.confirm_key_posted(key)
        return rows, tiers

    def compare(self, make_policy, raws):
        plain, _ = self.run_window(make_policy(), raws, capture=False)
        captured, tiers = self.run_window(make_policy(), raws, capture=True)
        self.assertEqual(plain, captured)
        return tiers

    def fixture_window(self, name):
        case = CASES[name]
        raws = boards(case)
        return self.compare(lambda: d57.loops.new_policy(
            dict(case, boards=raws), case["skill"], monraces=case.get("monraces")), raws)

    def test_dungeon_windows(self):
        self.assertGreater(self.fixture_window("n1b-325-low-hp-escape-1106.json.gz"), 0)
        self.assertGreater(self.fixture_window("death-n1a-450-1101.json.gz"), 0)

    def test_town_window(self):
        # Town is outside the design: no tiers are written there, and nothing changes.
        self.assertEqual(self.fixture_window("town-end-purchase-only-1102.json.gz"), 0)

    def test_quest_floor_window(self):
        raws = q25.CASE["boards"]
        tiers = self.compare(lambda: q25.new_policy(raws[0]), raws)
        self.assertGreater(tiers, 200)


if __name__ == "__main__":
    unittest.main()
