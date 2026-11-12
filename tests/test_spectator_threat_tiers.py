"""The spectator page's monster list carries each monster's threat tier (viewer only).

Owner 2026-11-08: 「脅威度の判定が入ったなら、観戦UIの見えているモンスター一覧にその判断を追記して。
脅威度順に色分けと、脅威度でのソートも入れて」.

Each listed hostile among the nearest ``SPECTATE_THREAT_MONSTERS`` is judged alone and from
contact (``threat_tiers.tiered([monster], contact=True)``, the judgement ``sensed_t1_leave_key``
uses); the board's engagement line is the decision row's own ``threat_tiers`` facts.  The list
is ordered 即死, T1, T2, T3, unknown, omitted, none, then by distance.

Recorded boards (the threat-tier tests' fixtures, tests/test_threat_tiers_recorded.py):
- summon-response-n1a-475-1104 at 2038858 (49F, nine hostiles): three T1 summoners, then T3.
- death-n1c-099-1102 at 691696 (Quest 31, fifteen hostiles): seven T1 before a T3 two cells away.
- death-n1a-475-1104 at 2039000 (49F, twenty listed): the bound of eight.
- n1b-325-low-hp-escape-1106 at 2100397 (Castle 33F): 智天使 alone is T1 (summon), jackals T3.
- q25-summons-n1b-312-1105 at 11653365 (Quest 25, nothing in view): no hostile.
- town-end-purchase-only-1102 (town): outside the design, no judgement.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import tempfile
import time
import unittest
from pathlib import Path

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle
from hengbot import spectator_threat, threat_tiers
from hengbot.cli import _capture_decision_facts, _spectator_threat
from hengbot.model import parse_snapshot
from hengbot.spectator import SpectatorWriter, spectator_details
from tests import test_plan_floor_summons_1105_recorded as summons
from tests.test_threat_tiers_recorded import CASES, boards, replay_to

T1, T3 = threat_tiers.T1, threat_tiers.T3


def recorded(name, turn):
    """(policy, board, raw state, the spectator's details) on a recorded board, the row first."""
    policy, board = replay_to(name, turn)
    raw = next(raw for raw in boards(CASES[name]) if raw["turn"] == turn)
    _capture_decision_facts(board, policy)
    return policy, board, raw, spectator_details(raw, board, _spectator_threat(policy, board))


def ordered(test, monsters):
    """The page's order: tier rank, then distance."""
    keys = [(spectator_threat.tier_rank(m.get("threat")), m["distance"]) for m in monsters]
    test.assertEqual(keys, sorted(keys))


def tiers(monsters):
    return [(m.get("threat") or {}).get("tier") for m in monsters]


class RecordedBoardsTest(unittest.TestCase):
    def test_summoners_first_n1a_475(self):
        _policy, _board, _raw, details = recorded("summon-response-n1a-475-1104.json.gz", 2038858)
        # Not 即死 since 2026-11-12 (t3-survival-1112 D: the game's spell choice and failure
        # lower these casters' next-action p95 below the HP); still T1.
        self.assertEqual(details["threat_engagement"],
                         {"tier": T1, "instant_death": False, "skipped": None, "t2_withheld": [],
                          "hostiles": 8})
        monsters = details["monsters"]
        self.assertEqual(tiers(monsters), [T1, T1, T1, T3, T3, T3, T3, T3, None])
        self.assertEqual([m["distance"] for m in monsters], [1, 1, 2, 2, 2, 3, 12, 15, 15])
        for row in monsters[:3]:
            self.assertEqual(row["threat"]["worsens_with_time"], ["summon"])
            self.assertIn("reward", row["threat"]["selected"])
            self.assertFalse(row["threat"]["instant_death"])
        self.assertEqual(monsters[-1]["threat"], {"omitted": "bound"})
        ordered(self, monsters)

    def test_a_far_t1_goes_before_a_near_t3_n1c_099(self):
        _policy, _board, _raw, details = recorded("death-n1c-099-1102.json.gz", 691696)
        monsters = details["monsters"]
        self.assertEqual(tiers(monsters)[:8], [T1] * 7 + [T3])
        self.assertEqual(monsters[7]["distance"], 2)
        self.assertGreater(monsters[6]["distance"], monsters[7]["distance"])
        ordered(self, monsters)

    def test_the_bound_is_the_nearest_eight_n1a_475(self):
        _policy, _board, raw, details = recorded("death-n1a-475-1104.json.gz", 2039000)
        monsters = details["monsters"]
        judged = [m for m in monsters if m.get("threat") and not m["threat"].get("omitted")]
        omitted = [m for m in monsters if (m.get("threat") or {}).get("omitted")]
        self.assertEqual(len(judged), spectator_threat.SPECTATE_THREAT_MONSTERS)
        self.assertEqual(len(judged) + len(omitted), 20)
        self.assertLessEqual(max(m["distance"] for m in judged),
                             min(m["distance"] for m in omitted))
        self.assertEqual(details["threat_engagement"]["tier"], T1)
        self.assertEqual(details["threat_engagement"]["hostiles"], 18)

    def test_each_monster_alone_n1b_325(self):
        _policy, board, _raw, details = recorded("n1b-325-low-hp-escape-1106.json.gz", 2100397)
        names = {m.index: m.race_id for m in board.visible_monsters}
        # T1 since n1-a life-514 (2026-11-12): the awake 智天使 (distance 8) reaches the player
        # over grids the board has not shown (owner 2026-11-08 「未知のマスを壁と見ない」), and its
        # spells join the engagement's projection (T3 before, when those grids read as walls).
        self.assertEqual(details["threat_engagement"]["tier"], T1)
        first = details["monsters"][0]
        self.assertEqual(first["threat"]["tier"], T1)
        self.assertEqual(first["threat"]["worsens_with_time"], ["summon"])
        cherub = next(m for m in board.visible_monsters if names[m.index] == 511)
        self.assertEqual(first["name"], cherub.name)
        self.assertEqual(tiers(details["monsters"][1:8]), [T3] * 7)
        ordered(self, details["monsters"])

    def test_the_engagement_is_the_decision_rows(self):
        policy, board = replay_to("death-n1a-450-1101.json.gz", 1268509)
        facts = _capture_decision_facts(board, policy)
        self.assertIs(spectator_threat.noted_engagement(board), facts["threat_tiers"])
        self.assertIsNone(spectator_threat.noted_engagement(copy.copy(board)))
        judgement = _spectator_threat(policy, board)
        self.assertEqual(judgement["engagement"],
                         spectator_threat.engagement_judgement(facts["threat_tiers"]))
        self.assertEqual(judgement["engagement"]["instant_death"], True)


class NoJudgementTest(unittest.TestCase):
    def test_a_board_with_no_hostile_q25(self):
        policy = summons._new_policy()
        raw = next(raw for raw in summons.CASE["boards"] if raw["turn"] == summons.QUIET_AT_THE_END)
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertFalse([m for m in (*board.visible_monsters, *board.detected_monsters)
                          if m.hostile])
        judgement = _spectator_threat(policy, board)
        self.assertEqual(judgement, {"engagement": {"tier": None, "instant_death": False,
                                                    "skipped": None, "t2_withheld": [],
                                                    "hostiles": 0},
                                     "monsters": {}})
        details = spectator_details(raw, board, judgement)
        self.assertEqual(details["threat_engagement"]["tier"], None)
        self.assertFalse([m for m in details["monsters"] if "threat" in m])

    def test_town_is_outside_the_design(self):
        name = "town-end-purchase-only-1102.json.gz"
        raw = boards(CASES[name])[0]
        policy, board = replay_to(name, raw["turn"])
        self.assertTrue(board.in_town)
        self.assertEqual(_spectator_threat(policy, board), {})
        self.assertNotIn("threat_engagement", spectator_details(raw, board, {}))

    def test_the_old_format_without_the_field(self):
        """Without a judgement (an old build, a failed one) the list is today's: by distance."""
        policy, board = replay_to("death-n1c-099-1102.json.gz", 691696)
        raw = next(raw for raw in boards(CASES["death-n1c-099-1102.json.gz"])
                   if raw["turn"] == 691696)
        details = spectator_details(raw, board)
        self.assertNotIn("threat_engagement", details)
        self.assertFalse([m for m in details["monsters"] if "threat" in m])
        distances = [m["distance"] for m in details["monsters"]]
        self.assertEqual(distances, sorted(distances))


class WriterTest(unittest.TestCase):
    def observe(self, writer, board, raw, threat):
        writer.observe(board, "a", "reason", 1, None, state_line=json.dumps(raw),
                       append_frame=True, threat=threat)

    def test_one_judgement_per_board_and_a_failure_is_no_judgement(self):
        policy, board = replay_to("n1b-325-low-hp-escape-1106.json.gz", 2100397)
        raw = next(raw for raw in boards(CASES["n1b-325-low-hp-escape-1106.json.gz"])
                   if raw["turn"] == 2100397)
        calls = []

        def threat():
            calls.append(1)
            return _spectator_threat(policy, board)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spectate.json"
            writer = SpectatorWriter(path, clock=iter(range(100, 200)).__next__)
            self.observe(writer, board, raw, threat)
            self.observe(writer, board, raw, threat)
            self.assertEqual(len(calls), 1)
            written = json.loads(path.read_text(encoding="utf-8"))
            # T1: the awake 智天使's reach over unknown grids (test_each_monster_alone_n1b_325).
            self.assertEqual(written["threat_engagement"]["tier"], T1)
            self.assertEqual(written["monsters"][0]["threat"]["tier"], T1)

            def failing():
                raise RuntimeError("judgement failed")

            other = copy.copy(board)
            stderr = []
            writer.stderr = type("S", (), {"write": lambda self, text: stderr.append(text),
                                           "flush": lambda self: None})()
            self.observe(writer, other, raw, failing)
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("threat_engagement", written)
            self.assertTrue(written["monsters"])
            self.assertIn("judgement failed", "".join(stderr))


class DecisionInvarianceTest(unittest.TestCase):
    """Judging the listed monsters after every decision (the production writer) changes no
    decided key or reason."""

    def run_window(self, name, judge):
        case = CASES[name]
        raws = boards(case)
        policy = replay_policy(case, raws)
        rows, judged = [], 0
        with tempfile.TemporaryDirectory() as directory:
            writer = SpectatorWriter(Path(directory) / "spectate.json")
            for raw in raws:
                board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
                key = str(policy.choose_key(board))
                rows.append((raw["turn"], key, policy.last_reason))
                _capture_decision_facts(board, policy)
                writer.observe(board, key, policy.last_reason, policy._decision_sequence, None,
                               state_line=json.dumps(raw), policy=policy, append_frame=True,
                               threat=(lambda: _spectator_threat(policy, board)) if judge else None)
                judged += judge and bool((writer.threat_board or (None, None))[1])
                if key:
                    policy.confirm_key_posted(key)
        return rows, judged

    def test_dungeon_windows(self):
        for name in ("n1b-325-low-hp-escape-1106.json.gz", "death-n1a-475-1104.json.gz"):
            with self.subTest(name=name):
                plain, _ = self.run_window(name, judge=False)
                judged_rows, judged = self.run_window(name, judge=True)
                self.assertEqual(plain, judged_rows)
                self.assertGreater(judged, 0)


class FollowLoopTest(unittest.TestCase):
    """The production follow loop (tests/test_spectator_frames.py's recorded exchange, the
    esp-threat-rest-20260921 boards): each posted frame carries the judgement, and the posts,
    keys and reasons are those of the loop without a spectator."""

    def test_frames_carry_the_judgement(self):
        from tests.test_spectator_frames import FramesFollowTest
        exchange = FramesFollowTest().exchange
        plain = exchange(spectate=False, recorded=True)
        run = exchange(recorded=True)
        self.assertEqual([(k, r) for k, r, _ in plain.posts], [(k, r) for k, r, _ in run.posts])
        self.assertEqual([(r["key"], r["reason"]) for r in plain.rows],
                         [(r["key"], r["reason"]) for r in run.rows])
        self.assertTrue(run.frames)
        for frame in run.frames:
            self.assertIn("threat_engagement", frame)
            self.assertTrue(any("threat" in m for m in frame["monsters"]))
            ordered(self, frame["monsters"])


def replay_policy(case, raws):
    from tests import test_n1c_deaths_1101_recorded as d57
    return d57.loops.new_policy(dict(case, boards=raws), case["skill"], monraces=case.get("monraces"))


class CostTest(unittest.TestCase):
    """The judgement runs on every posted board while a spectator writes: the slowest recorded
    boards stay cheap (measured 10-35 ms; the bound matches the threat-tier facts' CostTest).
    The fastest of three runs is compared, so a loaded machine does not fail it (one run took
    198 ms beside four parallel test processes)."""
    LIMIT_MS = 150
    RUNS = 3

    def test_the_deep_boards(self):
        for name, turn in (("summon-response-n1a-475-1104.json.gz", 2038858),
                           ("death-n1c-099-1102.json.gz", 691696)):
            with self.subTest(name=name):
                policy, board = replay_to(name, turn)
                _capture_decision_facts(board, policy)
                elapsed = []
                for _ in range(self.RUNS):
                    started = time.perf_counter()
                    _spectator_threat(policy, board)
                    elapsed.append((time.perf_counter() - started) * 1000)
                self.assertLess(min(elapsed), self.LIMIT_MS)


if __name__ == "__main__":
    unittest.main()
