"""D49 / D47: the recorded n1-c Magic-Eater town loops of 2026-10-31.

Boards are frozen in tests/fixtures/me-staff-loops-20261031.json.gz
(tests/extract_me_staff_loops_1031.py).  Every decision is the public
``choose_key``; every posted key goes through the production executor port
(test_me_nokey_1031_recorded.PostedKey).

* opening (life-066): Lv7, afraid beside 忍び寄る人形『メリー』.  The opening
  route meleed (cmd-attack.cpp: 「恐くて…を攻撃できない！」) seven times from
  one cell and stopped on quest:blocked:opening-route (no-progress:quest).
* inn (life-067): after stage 1 the walk from the Tower to Morivant's inn
  (me-staff:return-to-shop) scored no arbiter progress and quest-request
  retired four steps in (owner-retired-burst).
* tower (life-068): the Tower approach declared no Reach goal, so the
  town-blocked fuse counted every step and stopped on loop-detected.
* q2 (D47 life-065): Q2 TAKEN in Telmora; the finished sequence's
  me-staff:return-outpost teleported back to the Outpost every visit.

DECLARED CONSTRUCTED: each new process has read the staff power list
(``powers_read``); the sequence record is the capture's
``_me_staff_sequence`` (inn, tower) or every sequence staff absorbed (q2, the
sequence finished as recorded: its phase was ``return``); the q2 case borrows
the inn capture's ~f skill reply with the board's level (its capture keeps
player boards only); the tower fuse starts at the recorded 16 counted
decisions (one town:blocked line, 14 inn-walk steps, the teleport).  #47 D52
(the stage's buy round looks at each visited town's Magic shelf before the
Tower): the inn and tower cases declare the shelves the recorded run had
already seen in this restock wait (``searched_towns``), so their legs are
the recorded ones; both now ride the game's travel command
(test_me_tower_trips_recorded).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_staff_sequence as sequence
from hengbot.cli import TOWN_BLOCKED_STOP_LIMIT, _advance_town_blocked_iteration
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import ConservativePolicy
from hengbot.quest_strategies import load_quest_strategies
from tests import test_me_nokey_1031_recorded as nokey
from hengbot.town_travel import is_travel_macro


FIXTURE = Path(__file__).with_name("fixtures") / "me-staff-loops-20261031.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"
RECORDED_TOWER_FUSE = 16
# DECLARED CONSTRUCTED: the Home knowledge request is answered by a knowledge
# row the q2 capture does not keep, so its macro is not sent to the executor.
UNPOSTED = {"home:request-knowledge-scan"}


def new_policy(case, skill, *, record=None, monraces=None):
    policy = ConservativePolicy(quest_strategies=load_quest_strategies(STRATEGIES))
    for race, facts in (CASE["monraces"] if monraces is None else monraces).items():
        facts = copy.deepcopy(facts)
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
        policy._monrace_knowledge[int(race)] = MonraceKnowledge(**facts)
    first = case["boards"][0]
    policy.prime(parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(skill), turn=first["turn"],
        player=dict(skill["player"], level=first["player"]["level"])))
    if case.get("home"):
        policy.consume_home_knowledge(
            tuple(_parse_items(case["home"]["knowledge"]["items"], protocol=3)))
    state = sequence.state(policy)
    state.powers_read = True
    if record is not None:
        state.absorbed = {int(sval): count for sval, count in record["absorbed"].items()}
        state.bought = frozenset(record["bought"])
        state.shelf_after_turn = record["shelf_after_turn"]
        state.fundraise_why = record["fundraise_why"]
    return policy


def decide(policy, raw):
    return nokey.decide(policy, raw, None)


class MeStaffLoopsRecordedTest(nokey.PostedKey):
    def drive(self, policy, boards, each=None):
        rows = []
        for raw in boards:
            key = decide(policy, raw)
            rows.append((raw, key, policy.last_reason))
            if each is not None:
                each(raw, key)
            if key and policy.last_reason not in UNPOSTED:
                self.post(policy, raw, key)
            if key:
                policy.confirm_key_posted(key)
        return rows

    def test_afraid_opening_route_yields_to_the_survival_ladder(self):
        case = CASE["opening"]
        policy = new_policy(case, case["skill"])
        rows = self.drive(policy, case["boards"])
        for raw, key, reason in rows:
            self.assertTrue(raw["player"]["status"]["afraid"])
            self.assertNotEqual(reason, "melee", (raw["turn"], key))
            self.assertNotEqual(reason, "quest:blocked:opening-route", (raw["turn"], key))
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None))

    def test_walk_to_the_inn_after_stage1_is_arbiter_progress(self):
        case = CASE["inn"]
        policy = new_policy(case, case["skill"], record=case["sequence"])
        # DECLARED CONSTRUCTED: Morivant's Magic shelf seen in this wait.
        sequence.state(policy).searched_towns[2] = case["boards"][0]["turn"]
        reasons, keys = [], []

        def each(raw, key):
            telemetry = policy._town_turn_arbiter.telemetry or {}
            reasons.append(policy.last_reason)
            keys.append(key)
            if policy.last_reason == "me-staff:return-to-shop":
                self.assertTrue(telemetry.get("progress"), (raw["turn"], key, telemetry))
                self.assertFalse(policy._town_turn_arbiter.retirement_pending, raw["turn"])
                self.assertEqual((policy.decision_claim or {}).get("goal", {}).get("kind"),
                                 "Reach")

        self.drive(policy, case["boards"], each)
        self.assertEqual(set(reasons), {"me-staff:return-to-shop"})
        self.assertEqual(len(reasons), len(case["boards"]))
        self.assertTrue(is_travel_macro(keys[0]), keys[0])

    def test_tower_approach_closes_its_reach_goal_under_the_town_fuse(self):
        case = CASE["tower"]
        policy = new_policy(case, CASE["inn"]["skill"], record=case["sequence"])
        # DECLARED CONSTRUCTED: the Outpost's and Morivant's shelves seen in
        # this wait without Trap Location: the round is over, the Tower next.
        turn = case["boards"][0]["turn"]
        sequence.state(policy).searched_towns.update({0: turn, 2: turn})
        streak, durable = RECORDED_TOWER_FUSE, None
        reasons = []

        def each(raw, key):
            nonlocal streak, durable
            board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            streak, durable = _advance_town_blocked_iteration(
                policy, board, streak, durable, key=key)
            reasons.append(policy.last_reason)

        self.drive(policy, case["boards"], each)
        self.assertEqual(set(reasons), {"me-staff:approach-tower"})
        self.assertLess(streak, TOWN_BLOCKED_STOP_LIMIT)
        self.assertLessEqual(streak, RECORDED_TOWER_FUSE + 3)

    def test_finished_sequence_leaves_telmora_to_the_q2_errand(self):
        case = CASE["q2"]
        policy = new_policy(case, CASE["inn"]["skill"])
        state = sequence.state(policy)
        state.absorbed = {sval: 1 for sval in sequence.SEQUENCE_SVALS}
        rows = self.drive(policy, case["boards"])
        raw, key, reason = rows[-1]
        self.assertEqual(policy._effective_town_id(
            parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)), 1)
        self.assertFalse(reason.startswith("me-staff:"), (key, reason))
        self.assertNotIn("ma", key, reason)


if __name__ == "__main__":
    unittest.main()
