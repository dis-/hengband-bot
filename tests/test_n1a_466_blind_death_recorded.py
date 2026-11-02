"""Recorded replay of the n1-a life-466 death of 2026-11-03 02:31 (オークの洞窟14階).

Source: tests/fixtures/death-n1a-466-1103.json.gz
(tests/extract_n1a_466_blind_death_fixture.py): the Lv26 warrior's boards of
turns 3189880-3191559 (555 max HP, build 38c599427), the recorded decision
rows, and the floor's remembered terrain.

Beside a 腐った死体 a ヴラスタ (BITE:BLIND x2) blinded the player (3189929).
Ten Cure Critical Wounds and a Healing went on the blindness, each re-blinded
by the next bite; then the return walked blind to the known up-stair and,
below the low-HP threshold, the emergency ladder walked on
(``emergency:seek-upstairs``), bitten on almost every step, and died at HP 23
never having struck after the cures.  Build 38c599427 predates the fight
through of 8cd805c09; on main the blind boards still found no neighbour to
strike, because they draw only the walls beside the player and the remembered
floor the walk routes over was not asked, and the low-HP walk gate passed the
emergency step because no hostile was visible.

Owner rules: 「回復後即盲目になった場合は戦闘による状況打開を試みる。」
(2026-11-01, status_cure), 「近接で敵の方向が分からなければランダムな方向
に攻撃。」 (2026-10-03, unseen_strike) and the walk home strikes first
(2026-11-01 21h, answer 3).  Every decision is the public ``choose_key``; the
strike keys go through the production executor port.
DECLARED RECONSTRUCTED: the remembered terrain is the capture's death-time
policy state.
DECLARED CONSTRUCTED: the live bot never drank its Potion of Speed, so every
recorded board after the replay's first dose is shown hasted (speed field
+10, yellow; player-speed.cpp acceleration), and the stair case adds a
remembered up-stair on the cell the recorded emergency step went to.

Owner 2026-11-03 (answer): 「治してもまた盲目なら覚えている敵を攻撃。階段が
隣などとても近くにある場合を除き徒歩での逃走は絶対に間に合わない。また、
必要なら加速や体力回復など危険度に応じて物資を使用すること。」  Below the
low-HP threshold the first bitten board takes the carried Speed dose
(unseen_strike.speed_key; no heal potion was left, Cure Critical Wounds is
for the blindness), the hasted boards strike, and only a step onto an
up-stair is still walked.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import unseen_strike
from hengbot.model import Position
from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1a-466-1103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

BLINDED = 3189929        # 「ヴラスタに噛まれた。」「目が見えなくなってしまった！」
REBLINDED = 3189946      # re-blinded right after the first cure
CALM_STEP = 3190129      # no blow on the board: the walk home goes on
WALK_BITES = (3190142, 3190148)            # bitten on the walk, cures spent
SPEED_BITE = 3190630     # the first bite below the threshold
EMERGENCY_BITES = (3190642, 3191551)       # hasted, below the threshold
STRUCK = (REBLINDED,) + WALK_BITES + EMERGENCY_BITES
HASTED = {"speed": 120, "speed_display": {"color": "yellow", "riding": False,
                                          "text": "加速 (+10)", "value": 10}}


def new_policy():
    policy = d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
    terrain = CASE["terrain"]
    for name in ("known", "marked", "floor", "wall", "door", "rubble"):
        getattr(policy, f"_remembered_{name}_t").update(
            tuple(cell) for cell in terrain[f"{name}_t"])
    policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
    policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
    return policy


class BlindWalkBiterRecordedTest(d57.PostedDeathKey):
    def answers(self):
        """Decide every board; the strike and dose boards' keys go through
        the executor.  The boards after the first Speed dose are hasted."""
        policy, answers, hasted = new_policy(), {}, False
        for raw in CASE["boards"]:
            raw = copy.deepcopy(raw)
            if hasted:
                raw["player"].update(copy.deepcopy(HASTED))
            key = d57.loops.decide(policy, raw)
            answers[raw["turn"]] = (key, policy.last_reason)
            if raw["turn"] in (*STRUCK, SPEED_BITE):
                self.post(policy, raw, key)
            hasted = hasted or policy.last_reason == unseen_strike.SPEED_REASON
            policy.confirm_key_posted(key)
        return answers

    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        self.assertEqual(recorded[REBLINDED], ("item:cure-critical", "qc"))
        for turn in (CALM_STEP,) + WALK_BITES:
            self.assertEqual(recorded[turn][0], "return:seek-upstairs", turn)
        for turn in EMERGENCY_BITES:
            self.assertEqual(recorded[turn][0], "emergency:seek-upstairs", turn)
        rows = {raw["turn"]: raw for raw in CASE["boards"]}
        self.assertIn("ヴラスタに噛まれた。", rows[BLINDED]["messages"])
        self.assertEqual(rows[WALK_BITES[0]]["messages"], ["噛まれた。"])
        self.assertTrue(all(rows[turn]["player"]["status"]["blind"] for turn in STRUCK))

    def test_blind_walks_strike_the_unseen_biter(self):
        answers = self.answers()
        self.assertEqual(answers[BLINDED], ("qc", "item:cure-critical"))
        self.assertEqual(answers[CALM_STEP][1], "return:seek-upstairs")
        for turn in (REBLINDED,) + WALK_BITES:
            key, reason = answers[turn]
            self.assertEqual((key[:1], reason), ("+", "blind:fight-through"), turn)
        speed = next(item["slot"] for item in CASE["boards"][-1]["inventory"]
                     if item["name"].startswith("スピードの薬"))
        self.assertEqual(answers[SPEED_BITE], ("q" + speed, unseen_strike.SPEED_REASON))
        for turn in EMERGENCY_BITES:
            key, reason = answers[turn]
            self.assertEqual((key[:1], reason), ("+", "no-wait:attack"), turn)

    def test_step_onto_an_up_stair_still_escapes(self):
        policy, raw = new_policy(), None
        for board in CASE["boards"]:
            board = copy.deepcopy(board)
            if board["turn"] > SPEED_BITE:
                board["player"].update(copy.deepcopy(HASTED))
            if board["turn"] == EMERGENCY_BITES[0]:
                raw = board
                break
            policy.confirm_key_posted(d57.loops.decide(policy, board))
        recorded = d57.recorded(CASE)[raw["turn"]]
        self.assertEqual(recorded, ("emergency:seek-upstairs", "9"))
        here = raw["player"]["y"], raw["player"]["x"]
        policy._remembered_upstairs.add(Position(here[0] - 1, here[1] + 1))
        key = d57.loops.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("9", "emergency:seek-upstairs"))
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
