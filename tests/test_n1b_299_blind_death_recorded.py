"""Recorded replay of the n1-b life-299 death of 2026-11-03 01:26 (オークの洞窟19階).

Source: tests/fixtures/death-n1b-299-1103.json.gz
(tests/extract_n1b_299_blind_death_fixture.py): the Lv26 warrior's boards of
turns 930959-931557 (516 max HP, build 476464048), the recorded decision rows,
and the floor's remembered terrain.

A ヴラスタ (race 249, Lv14, 12d6 HP, BITE:BLIND x2) came out of the dark
during a rest and blinded the player before any sighted board showed it, so
blind_strike remembered no attacker beside it.  The seven Cure Critical
Wounds went on the blindness, each re-blinded by the next bite (931209-931269:
「やっと目が見えるようになった。」 then 「ヴラスタに噛まれた。」「目が見えなく
なってしまった！」), then the return walked blind to the known up-stair,
bitten on almost every step (「何かに噛まれた。」, or the later blow's bare
「噛まれた。」), through three traps, and died at HP 2 never having struck.

Owner rules: 「回復後即盲目になった場合は戦闘による状況打開を試みる。」
(2026-11-01, status_cure) and 「近接で敵の方向が分からなければランダムな方向
に攻撃。」 (2026-10-03, unseen_strike); the walk home strikes first
(2026-11-01 21h, answer 3 「どちらも先に反撃」).  Every decision is the public
``choose_key``; the strike keys go through the production executor port.
DECLARED RECONSTRUCTED: the remembered terrain is the capture's death-time
policy state (blind from turn 931209 on, the player memorised no cell after
it).  DECLARED CONSTRUCTED: the walk-home case strips the Cure Critical Wounds
from the boards from 931209 on, as it states.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position
from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1b-299-1103.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

FIRST, BLINDED, LAST = 931151, 931209, 931306
CURE_BOARDS = (931209, 931218, 931233, 931244, 931252, 931258, 931269)
REBLINDED_HIT = 931233   # 「何かに噛まれた。」 after the second cure
CURES_SPENT = 931280     # the first board with no Cure Critical Wounds
BARE_BLOW = 931296       # 「噛まれた。」 alone
CALM_STEP = 931289       # no blow on the board
CURE_CRITICAL = "致命傷の治癒の薬"
STRUCK = (REBLINDED_HIT, CURES_SPENT, BARE_BLOW)


def new_policy():
    policy = d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
    terrain = CASE["terrain"]
    for name in ("known", "marked", "floor", "wall", "door", "rubble"):
        getattr(policy, f"_remembered_{name}_t").update(
            tuple(cell) for cell in terrain[f"{name}_t"])
    policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
    policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
    return policy


def boards(*, cures=True):
    rows = []
    for raw in CASE["boards"]:
        if FIRST <= raw["turn"] <= LAST:
            raw = copy.deepcopy(raw)
            if not cures and raw["turn"] >= BLINDED:
                raw["inventory"] = [item for item in raw["inventory"]
                                    if CURE_CRITICAL not in item["name"]]
            rows.append(raw)
    return rows


class BlindBiterRecordedTest(d57.PostedDeathKey):
    def answers(self, *, cures=True):
        """Decide every board; the strike boards' keys go through the executor."""
        policy, answers = new_policy(), {}
        for raw in boards(cures=cures):
            key = d57.loops.decide(policy, raw)
            answers[raw["turn"]] = (key, policy.last_reason)
            if raw["turn"] in STRUCK:
                self.post(policy, raw, key)
            policy.confirm_key_posted(key)
        return answers

    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        self.assertEqual({recorded[turn] for turn in CURE_BOARDS},
                         {("item:cure-critical", "qa")})
        for turn in (CALM_STEP, CURES_SPENT, BARE_BLOW):
            self.assertEqual(recorded[turn], ("return:seek-upstairs", "8"), turn)
        rows = {raw["turn"]: raw for raw in CASE["boards"]}
        self.assertFalse(rows[BLINDED - 48]["player"]["status"]["blind"])
        self.assertEqual(rows[BLINDED]["visible_monsters"], [])
        self.assertEqual(rows[BARE_BLOW]["messages"], ["噛まれた。"])
        self.assertIn("何かに噛まれた。", rows[REBLINDED_HIT]["messages"])
        self.assertIn("ヴラスタに噛まれた。", rows[BLINDED]["messages"])

    def test_reblinded_hit_is_fought_through_instead_of_the_cure(self):
        answers = self.answers()
        self.assertEqual(answers[BLINDED], ("qa", "item:cure-critical"))
        for turn in STRUCK:
            key, reason = answers[turn]
            self.assertEqual((key[:1], reason), ("+", "blind:fight-through"), turn)

    def test_blind_walk_home_strikes_the_unseen_biter_first(self):
        answers = self.answers(cures=False)
        self.assertEqual(answers[CALM_STEP], ("8", "return:seek-upstairs"))
        for turn in STRUCK:
            key, reason = answers[turn]
            self.assertEqual((key[:1], reason), ("+", "unseen:strike-return"), turn)


if __name__ == "__main__":
    unittest.main()
