"""Recorded replay of the n1-b life-306 death of 2026-11-04 01:54 (鉄獄19階).

Source: tests/fixtures/death-n1b-306-1104.json.gz
(tests/extract_n1b_306_blind_death_fixture.py): the Lv26 warrior's boards of
turns 4876566-4877039 (458 max HP) and the recorded decision rows.

A ヴラスタ (race 249, BITE:BLIND x2) blinded it and re-blinded it right after
its Cure Critical Wounds, which latched the blindness (status_cure).  The bites
ended two boards later (「何かを殺した。」, turn 4876693) but the latch held to the
death, 35 strikes later, under 赤オクタロック's crush and shots, with nine Cure
Critical Wounds, four Potions of Speed and fifteen Teleport scrolls in the pack.

Owner rules: 「回復後即盲目になった場合は戦闘による状況打開を試みる。…HPが減ったら
体力回復かテレポート。」 (2026-11-01) and 「治してもまた盲目なら覚えている敵を攻撃。…
必要なら加速や体力回復など危険度に応じて物資を使用すること。」 (2026-11-03).
Curing blindness with Cure Critical Wounds is fine; it is no HP recovery.

DECLARED CONSTRUCTED: SpeedBeforeStrikeRecordedTest takes the Cure Critical
Wounds out of the boards after the first cure, so the lethal ladder reaches its
last answers on the recorded crush boards (what a biter still biting would do).
Its strike at the remembered cell retires after 「何もない空中を攻撃した。」
(blind_strike), so its boards past that are the recorded strikes' boards only.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import Position
from tests import test_n1c_deaths_1101_recorded as d57


FIXTURE = Path(__file__).with_name("fixtures") / "death-n1b-306-1104.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

CURE, REBLINDED, BITTEN, BITES_ENDED = 4876662, 4876673, 4876687, 4876693
# HP 290 and 216, both with a crush on the board; the threshold is 229.
ABOVE_THRESHOLD, BELOW_THRESHOLD = 4876845, 4876897
CURE_CRITICAL = "致命傷の治癒の薬"


def new_policy():
    policy = d57.loops.new_policy(CASE, CASE["skill"], monraces=CASE["monraces"])
    terrain = CASE["terrain"]
    for name in ("known", "marked", "floor", "wall", "door", "rubble"):
        getattr(policy, f"_remembered_{name}_t").update(
            tuple(cell) for cell in terrain[f"{name}_t"])
    policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
    return policy


def boards(*, cures=True):
    rows = copy.deepcopy(CASE["boards"])
    if not cures:
        for raw in rows:
            if raw["turn"] > CURE:
                raw["inventory"] = [item for item in raw["inventory"]
                                    if CURE_CRITICAL not in item["name"]]
    return rows


class LatchOutlivesTheBlinderRecordedTest(d57.PostedDeathKey):
    def answers(self, *, until):
        policy, answers = new_policy(), {}
        for raw in boards():
            if raw["turn"] > until:
                break
            key = d57.loops.decide(policy, raw)
            answers[raw["turn"]] = (key, policy.last_reason)
            if raw["turn"] in (BITTEN, BITES_ENDED):
                self.post(policy, raw, key)
            policy.confirm_key_posted(key)
        return answers

    def test_recorded_rows(self):
        recorded = d57.recorded(CASE)
        self.assertEqual(recorded[BITES_ENDED], ("blind:fight-through", "+9"))
        self.assertEqual(recorded[BELOW_THRESHOLD], ("emergency:blind-strike", "+9"))
        rows = {raw["turn"]: raw for raw in CASE["boards"]}
        self.assertIn("目が見えなくなってしまった！", rows[REBLINDED]["messages"])
        self.assertIn("何かに噛まれた。", rows[BITTEN]["messages"])
        for raw in CASE["boards"]:
            if raw["turn"] >= BITES_ENDED:
                self.assertTrue(raw["player"]["status"]["blind"], raw["turn"])
                self.assertFalse([m for m in raw["messages"] if m.endswith("噛まれた。")], raw["turn"])
        pack = {item["name"]: item["count"] for item in CASE["boards"][-1]["inventory"]}
        self.assertEqual((pack[CURE_CRITICAL], pack["スピードの薬"], pack["テレポートの巻物"]), (9, 4, 15))

    def test_the_cure_returns_when_the_re_blinding_bite_stops(self):
        answers = self.answers(until=BITES_ENDED)
        self.assertEqual(answers[CURE], ("qd", "item:cure-critical"))
        for turn in (REBLINDED, BITTEN):
            self.assertEqual(answers[turn], ("+9", "blind:fight-through"), turn)
        self.assertEqual(answers[BITES_ENDED], ("qd", "item:cure-critical"))


    def test_the_carried_cure_answers_every_board_without_the_bite(self):
        # The recorded boards stay blind, as the recorded strikes left them, so
        # each one asks again; none of them walks blind with the cures carried.
        policy = new_policy()
        for raw in boards():
            key = d57.loops.decide(policy, raw)
            if raw["turn"] >= BITES_ENDED:
                self.assertEqual(key, "qd", (raw["turn"], policy.last_reason))
            policy.confirm_key_posted(key)


class SpeedBeforeStrikeRecordedTest(d57.PostedDeathKey):
    def test_lethal_ladder_takes_the_speed_dose_below_the_low_hp_threshold(self):
        policy, answers = new_policy(), {}
        for raw in boards(cures=False):
            key = d57.loops.decide(policy, raw)
            answers[raw["turn"]] = (key, policy.last_reason)
            if raw["turn"] == BELOW_THRESHOLD:
                self.post(policy, raw, key)
                break
            policy.confirm_key_posted(key)
        key, reason = answers[ABOVE_THRESHOLD]
        self.assertEqual((key[:1], reason), ("+", "emergency:unseen-strike"))
        self.assertEqual(answers[BELOW_THRESHOLD], ("qc", "unseen:quaff-speed"))


if __name__ == "__main__":
    unittest.main()
