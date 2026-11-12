"""Quest 25 on n1-b life-378 (2026-11-13 01:46-01:47): every phase ended, the quest not won, recorded.

n1-b life-378 (Magic-Eater Lv37, build bot-68c820fd6) had ended every phase of the plan
(quest25_battle ``phase`` 11 in its battle record) with the quest (KILL_ALL) still taken: the
quylthulgs' phase had found no ball and was skipped (owner 2026-11-06 phase3 「範囲攻撃が無ければ
1) をとばして」), and the sweep's Detect Evil showed nothing (a quylthulg is not evil).  With no
phase left the plan had no step, the navigator answered ``quest:blocked:execute`` ('5') on [12,24]
every decision, and the loop guard stopped the bot three times (01:47:00, 01:47:07, 01:47:14).

Now ``quest25_battle._after_the_phases``: each quylthulg still on its cell is shot directly from
its line (phase3 「加速して直接撃つ」, owner 2026-11-05 「最後ドルジの前に処理する」), then the
sweep's round is walked (phase6_sweep 「巡回して探す」, bounded by room_sweep.max_rounds).

Recorded: tests/fixtures/n1b-378-q25-blocked-1113.json.gz
(tests/extract_n1b_378_q25_blocked_1113_fixture.py): the restarted process's boards (decisions
0-39, all on [12,24]) and the battle record the bot kept beside its decision log.  A fresh policy
restores the record through the real path (quest25_battle_record) and decides the boards through
the public ``choose_key``.

DECLARED: the record is the one the last process left (turn 2944599, 01:47:14); its turn is set to
the first board's (2944062) so the restore takes it (the battle it carries was the same at
01:47:07: every phase ended, nothing killed since).  The restart's periodic reads (decisions 0-3)
are not issued by this harness.  ``test_the_walk_goes_on_without_turning_back`` is CONSTRUCTED:
the board of decision 4 at full HP, the player moved one cell per walk key.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import kill_all_patrol, quest25_battle as battle
from hengbot.model import parse_snapshot
from tests.support import q25_house as q25

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-378-q25-blocked-1113.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

BLOCKED = "quest:blocked:execute"
STEP = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1), "7": (-1, -1),
        "8": (-1, 0), "9": (-1, 1)}


def new_policy(directory: Path):
    boards = CASE["second"]["boards"]
    record = dict(CASE["battle_record"], turn=boards[0]["turn"])   # DECLARED (module note)
    (directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy._q25_battle_record_path = directory / "q25-battle.json"
    policy._warning_cell_record_path = directory / "warning-cells.json"
    first = copy.deepcopy(boards[0])
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first["turn"],
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    return policy


def decide(policy, raw):
    key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
    if key is not None:
        policy.confirm_key_posted(key)
    return key, policy.last_reason


def replay(*, patches=()):
    with TemporaryDirectory() as directory, _patched(patches):
        policy = new_policy(Path(directory))
        answers = [decide(policy, raw) for raw in CASE["second"]["boards"][4:]]
        phase = policy._quest_navigators[25].phase_battle.phase
    return answers, phase


class _patched:
    def __init__(self, patches):
        self.patches = [patch.object(*spec) for spec in patches]

    def __enter__(self):
        for each in self.patches:
            each.start()

    def __exit__(self, *_exc):
        for each in reversed(self.patches):
            each.stop()


NO_AFTER = ((battle, "_after_the_phases", lambda _ctx: None),)
# The KILL_ALL patrol the navigator asks when a plan has no step (owner 2026-11-13, kill_all_patrol).
NO_PATROL = ((kill_all_patrol, "key", lambda *_args: None),)


class BlockedExecuteRecordedTest(unittest.TestCase):

    def test_the_recording(self):
        rows = CASE["second"]["recorded"]
        self.assertEqual({(row["key"], row["reason"]) for row in rows[4:]}, {("5", BLOCKED)})
        self.assertEqual({(board["player"]["y"], board["player"]["x"])
                          for board in CASE["second"]["boards"]}, {(12, 24)})
        fight = CASE["battle_record"]["battle"]
        self.assertEqual(fight["phase"], len(battle.PHASES))
        kills = dict((race, count) for race, count in fight["kills"]["dict"])
        self.assertNotIn(480, kills)               # no quylthulg killed
        self.assertEqual(fight["quyls_done"], {"set": []})

    def test_every_board_has_a_step_now(self):
        answers, phase = replay()
        self.assertEqual(phase, len(battle.PHASES))
        self.assertNotIn(BLOCKED, {reason for _key, reason in answers})
        self.assertEqual(answers[0], ("9", battle.SIGHT_REASON))   # toward a cell that sees [9,13]

    def test_control_without_it_the_plan_has_no_step(self):
        answers, _phase = replay(patches=NO_AFTER + NO_PATROL)
        self.assertEqual(set(answers), {("5", BLOCKED)})

    def test_without_it_the_kill_all_patrol_still_answers(self):
        # The navigator's safety net for every KILL_ALL plan (kill_all_patrol).
        answers, _phase = replay(patches=NO_AFTER)
        self.assertNotIn(BLOCKED, {reason for _key, reason in answers})
        self.assertTrue({reason for _key, reason in answers} <= {
            kill_all_patrol.WALK_REASON, kill_all_patrol.DETECT_REASON, kill_all_patrol.HUNT_REASON})

    def test_the_walk_goes_on_without_turning_back(self):
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory))
            raw = copy.deepcopy(CASE["second"]["boards"][4])
            raw["messages"], raw["player"]["hp"] = [], raw["player"]["max_hp"]
            cells = []
            for _ in range(30):
                key, reason = decide(policy, raw)
                self.assertNotEqual(reason, BLOCKED)
                cells.append((raw["player"]["y"], raw["player"]["x"]))
                dy, dx = STEP[key]
                raw["player"]["y"] += dy
                raw["player"]["x"] += dx
                raw["turn"] += 10
        self.assertEqual(len(cells), len(set(cells)), cells)   # no cell walked twice
        self.assertEqual(cells[:6], [(12, 24), (11, 25), (10, 24), (9, 23), (8, 22), (8, 21)])


if __name__ == "__main__":
    unittest.main()
