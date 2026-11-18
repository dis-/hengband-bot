"""Quest 25 on n1-c life-217 (2026-11-19 05:24): teleported into the dreadmaster's range, recorded.

n1-c life-217 (Magic-Eater Lv38, build bot-c9bb90888) was in the tome's phase (quest25_battle
``phase`` 5) when the nexus quylthulg teleported it into the east room (「ネクサス・クイルスルグに
テレポートさせられた。」, decision 8194, (7,26)).  The only way back west is the north corridor's
[1,18], where a corpse mass sat; every cell with a line to it lies in the dreadmaster's sensing
range, where phase4 does not shoot the masses from (「ドリードマスターの感知範囲の外」).  With no way
to the tome and no mass to shoot, the plan had no step on [8,20]: ``quest:blocked:execute`` 32
times to the loop guard.

Owner 2026-11-19 (verbatim): 「テレポートで飛ばされてドリードマスターの感知範囲内に行ってしまったら
優先してドリードマスターを倒す」.  ``_teleported_dreadmaster_key``: after a monster's teleport into
that range the dreadmaster phase's fight comes first (the breeders in line still shot when it
walks or holds), until it is dead or the player is out of range.  With it dead the range no longer
shuts the masses' cells, and a phase with no step walks to the cell that reaches the most masses
(owner 2026-11-08 「道をふさがれたら待たずに撃って開ける」, ``_act``).

The 「「食地 臓臓 扈知」と書かれた巻物は燃えてしまった！」 line of decision 8206 is a floor scroll the
fire ball burnt (effect/effect-item.cpp: the item's name and 「燃えてしまった！」), no kill: the plan
does not read it as one (``_killed_name``).

Recorded: tests/fixtures/n1c-217-q25-tome-blocked-1119.json.gz
(tests/extract_n1c_217_q25_tome_blocked_1119_fixture.py), boards 8121-8237.  A fresh policy
restores the battle record through the real path (quest25_battle_record) and decides the boards
through the public ``choose_key``.  DECLARED: the record is the stop's (turn 3582917); its turn is
set to the first decided board's (decision 8193, the board before the teleport), so the masses
killed after it count as already killed.  The policy holds the magic-eater lists of the visit's
town arrival (05:10:33) and its ~f reading (the ring carries neither).  The dead dreadmaster test is
CONSTRUCTED: its kill set on the battle.

The restart (2026-11-19 05:59, build bot-d3b86d8e9, the rule in): the restarted process found the
player on [8,20] with the teleport line long gone (its battle record, restored from before the
mark existed, carries it unset), and waited 35 times to the loop guard.  ``_stranded_in_dread_range_key``: a phase with no
step while the player stands in the living dreadmaster's range is the same displacement (no phase
before the dreadmaster's stops there by its plan).  The restart's boards (decisions 4-39; 0-3 are
its periodic reads) are decided by a fresh policy restoring that record, without magic-eater lists
(not carried across a restart, as live).

Owner 2026-11-19 (verbatim): 「ドリードマスターを優先撃破する決まりのとき、邪魔なら死体の塊を倒して
良い」.  In that fight, with the way to its stand shut on the player's cell (the mass on [1,18]), the
walk goes to the cell that reaches the most masses with the dreadmaster's range not shunned, and
the shot there opens the way.  ``test_the_walk_reaches_a_line_and_shoots_the_mass`` is
CONSTRUCTED: the restart's first plan board, the player moved one cell per walk key.
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
from hengbot import quest25_battle as battle
from hengbot import quest25_geometry as geo
from hengbot.model import parse_snapshot
from hengbot.unseen_strike import message_text
from tests.support import q25_house as q25

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-217-q25-tome-blocked-1119.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

BLOCKED = "quest:blocked:execute"
START = 72        # decision 8193, before the teleport
TELEPORTED = 73   # decision 8194: 「…にテレポートさせられた。」, (7,26)
WALL = 85         # decision 8206: the first blocked wait on [8,20]


def new_policy(directory: Path, start: int):
    boards = CASE["boards"]
    record = dict(CASE["battle_record"], turn=boards[start]["turn"])   # DECLARED (module note)
    (directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy._q25_battle_record_path = directory / "q25-battle.json"
    policy._warning_cell_record_path = directory / "warning-cells.json"
    two_weapon, shield = CASE["skill_exp"]
    first = boards[start]
    policy.consume_skill_knowledge({
        "knowledge": {"skills": [{"id": 1, "exp": two_weapon}, {"id": 3, "exp": shield}]},
        "turn": first["turn"], "player": {"level": first["player"]["level"]}})
    policy.prime(parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge))
    policy._me_device_lists = {kind: (turn, tuple(rows)) for kind, (turn, rows) in CASE["lists"].items()}
    return policy


def decide(policy, raw):
    key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
    if key:
        policy.confirm_key_posted(key)
    return key, policy.last_reason


def replay(start=START):
    with TemporaryDirectory() as directory:
        policy = new_policy(Path(directory), start)
        answers = []
        for raw in CASE["boards"][start:]:
            answers.append(decide(policy, raw))
            answers[-1] += (policy._quest_navigators[25].phase_battle.dread_teleported,)
    return answers


def replay_restart():
    restart = CASE["restart"]
    boards = restart["boards"]
    with TemporaryDirectory() as directory:
        directory = Path(directory)
        (directory / "q25-battle.json").write_text(
            json.dumps(dict(restart["battle_record"], turn=boards[0]["turn"])), encoding="utf-8")
        policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                    quest_strategies=q25.STRATEGIES)
        policy._q25_battle_record_path = directory / "q25-battle.json"
        policy._warning_cell_record_path = directory / "warning-cells.json"
        two_weapon, shield = CASE["skill_exp"]
        policy.consume_skill_knowledge({
            "knowledge": {"skills": [{"id": 1, "exp": two_weapon}, {"id": 3, "exp": shield}]},
            "turn": boards[0]["turn"], "player": {"level": boards[0]["player"]["level"]}})
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), policy._monrace_knowledge))
        answers = [decide(policy, raw) for raw in boards[4:]]
        flag = policy._quest_navigators[25].phase_battle.dread_teleported
    return answers, flag


class RestartRecordedTest(unittest.TestCase):

    def test_the_recording(self):
        restart = CASE["restart"]
        reasons = [row["reason"] for row in restart["recorded"][4:]]
        # Every plan decision a blocked wait (one Speed cast by the strong-fight rung between them).
        self.assertEqual(set(reasons) - {BLOCKED}, {"quest-strategy:quaff-speed:absorbed-power"})
        self.assertGreaterEqual(reasons.count(BLOCKED), 35)
        self.assertFalse(restart["battle_record"]["battle"]["dread_teleported"])
        self.assertFalse(any(message_text(message).endswith("にテレポートさせられた。")
                             for board in restart["boards"] for message in board["messages"]))

    def test_the_restart_fights_the_dreadmaster_instead_of_waiting(self):
        answers, flag = replay_restart()
        self.assertTrue(flag)
        self.assertNotIn(BLOCKED, {reason for _key, reason in answers})

    def test_the_walk_reaches_a_line_and_shoots_the_mass(self):
        restart = CASE["restart"]
        boards = restart["boards"]
        step = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1), "6": (0, 1),
                "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "q25-battle.json").write_text(
                json.dumps(dict(restart["battle_record"], turn=boards[0]["turn"])), encoding="utf-8")
            policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                        quest_strategies=q25.STRATEGIES)
            policy._q25_battle_record_path = directory / "q25-battle.json"
            policy._warning_cell_record_path = directory / "warning-cells.json"
            two_weapon, shield = CASE["skill_exp"]
            policy.consume_skill_knowledge({
                "knowledge": {"skills": [{"id": 1, "exp": two_weapon}, {"id": 3, "exp": shield}]},
                "turn": boards[0]["turn"], "player": {"level": boards[0]["player"]["level"]}})
            policy.prime(parse_snapshot(copy.deepcopy(boards[0]), policy._monrace_knowledge))
            raw = copy.deepcopy(boards[4])
            raw["messages"] = []
            walked = []
            for _ in range(12):
                key, reason = decide(policy, raw)
                if key not in step:
                    break
                self.assertEqual(reason, battle.MASS_CELL_REASON)
                walked.append((raw["player"]["y"], raw["player"]["x"]))
                dy, dx = step[key]
                raw["player"]["y"] += dy
                raw["player"]["x"] += dx
                raw["turn"] += 10
        self.assertEqual(walked, [(8, 20), (7, 19), (6, 19), (5, 19), (4, 19)])
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), (3, 19))
        self.assertEqual(reason, battle.SHOT_REASON)   # at the mass on [1,18]
        self.assertTrue(key.startswith("f"))

    def test_control_without_it_the_restart_is_blocked(self):
        with patch.object(battle, "_stranded_in_dread_range_key", lambda _ctx: None):
            answers, _flag = replay_restart()
        self.assertIn(("5", BLOCKED), set(answers))


class TomeBlockedRecordedTest(unittest.TestCase):

    def test_the_recording(self):
        rows = CASE["recorded"]
        self.assertEqual({(row["key"], row["reason"]) for row in rows[WALL:]}, {("5", BLOCKED)})
        texts = [message_text(message) for message in CASE["boards"][TELEPORTED]["messages"]]
        self.assertTrue(any(text.endswith("にテレポートさせられた。") for text in texts), texts)
        self.assertEqual(CASE["battle_record"]["battle"]["phase"], battle.phase_index("tome"))

    def test_the_teleport_puts_the_dreadmaster_first_and_nothing_blocks(self):
        answers = replay()
        recorded = CASE["recorded"][START:]
        self.assertFalse(answers[0][2])
        self.assertTrue(all(flag for _key, _reason, flag in answers[1:]))
        # Up to the wall the shots and walks are the recorded ones (the masses in line first).
        for index in range(TELEPORTED - START, WALL - START):
            self.assertEqual(answers[index][:2], (recorded[index]["key"], recorded[index]["reason"]),
                             index + START)
        self.assertNotIn(BLOCKED, {reason for _key, reason, _flag in answers})
        # On [8,20] the way to its stand is shut by the mass on [1,18]: owner 2026-11-19 「邪魔なら
        # 死体の塊を倒して良い」, the walk to a cell with a line to it, its range not shunned.
        self.assertEqual(set(answers[WALL - START:]), {("7", battle.MASS_CELL_REASON, True)})

    def test_control_without_it_the_plan_is_blocked(self):
        with patch.object(battle, "_teleported_dreadmaster_key", lambda _ctx: None):
            answers = replay()
        self.assertIn(("5", BLOCKED), {answer[:2] for answer in answers[WALL - START:]})

    def test_the_dreadmaster_dead_the_masses_way_is_opened(self):
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), WALL + 1)
            decide(policy, CASE["boards"][WALL + 1])
            fight = policy._quest_navigators[25].phase_battle
            fight.kills = {**fight.kills, geo.DREADMASTER: 1}   # CONSTRUCTED
            key, reason = decide(policy, CASE["boards"][WALL + 2])
        self.assertEqual(reason, battle.MASS_CELL_REASON)
        self.assertTrue(key)

    def test_the_burnt_scroll_is_no_kill(self):
        texts = [message_text(message) for message in CASE["boards"][WALL]["messages"]]
        burnt = next(text for text in texts if text.endswith("燃えてしまった！"))
        self.assertIsNone(battle._killed_name(burnt))


if __name__ == "__main__":
    unittest.main()
