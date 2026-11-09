"""Recorded replay of n1-a life-504's arrival on 鉄獄24階 (random quest 41), 2026-11-10.

Source: tests/fixtures/n1a-504-blind-1110.json.gz (tests/extract_n1a_504_blind_rest_fixture.py),
boards of turns 877017-877691 and 880383-880451.  The light hounds' flash breaths
(「ライト・ハウンドが閃光のブレスを吐いた。」) blinded the player again and again; it drank a
Cure Critical Wounds or a Healing for each blindness at HP 487-516 (the server log of the
run, C:/hengband-backups/pdca/captures/n1a-504-death-1110/rq24-reblind-cures-877k.txt: nine
Cure Critical Wounds 877156-877416, three Healing 877463-877561 and the last at 880417).
Each blindness was randint1(5) + 2 ticks (effect-player-resist-hurt.cpp:412).  Seventeen
thousand game turns later a gas trap blinded it with no cure left (test_n1a_504_blind_rest_recorded).

Owner 2026-11-10 (G1) 「飲まずに戦うか待つ」: 「HP が高く、光・閃光・暗黒のブレスによる短い盲目なら
治療薬を使わず、隣の敵は殴り、いなければ治るまで待つ。治療薬は罠などの長い盲目や HP が減った時の
ために残す。」 (Owner 2026-11-10 (G2) 「0本になったら帰還」 is test_n1a_504_blind_cure_return_recorded.)
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot.status_cure import (
    SHORT_BLIND_MELEE_REASON, SHORT_BLIND_STRIKE_REASON, SHORT_BLIND_WAIT_REASON)
from tests.test_n1a_504_blind_rest_recorded import CASE, GAS_TRAP, LANDING, boards, decide, new_policy


# The boards on which the run drank a cure for a flash-breath blindness (the server log).
CURED = (877156, 877172, 877182, 877212, 877252, 877290, 877317, 877382, 877416, 877463,
         877525, 877561)
LAST_HEALING = 880417
SHORT = {SHORT_BLIND_MELEE_REASON, SHORT_BLIND_WAIT_REASON, SHORT_BLIND_STRIKE_REASON}
CURE_CRITICAL = "致命傷の治癒の薬"


def run(first, last, edit=None):
    policy, answers = new_policy(first), {}
    for raw in boards(first, last):
        if edit is not None:
            edit(raw)
        key = decide(policy, raw)
        answers[raw["turn"]] = (key, policy.last_reason)
        policy.confirm_key_posted(key)
    return answers


def cure_row():
    """The Cure Critical Wounds row of the arrival's first cure board (the recorded pack)."""
    raw = next(raw for raw in CASE["boards"] if raw["turn"] == CURED[0])
    return copy.deepcopy(next(item for item in raw["inventory"] if CURE_CRITICAL in item["name"]))


class ShortBlindRecordedTest(unittest.TestCase):
    def test_recorded_boards(self):
        rows = {raw["turn"]: raw for raw in CASE["boards"]}
        turns = sorted(rows)
        for turn in CURED + (LAST_HEALING,):
            raw = rows[turn]
            self.assertTrue(raw["player"]["status"]["blind"], turn)
            self.assertGreaterEqual(raw["player"]["hp"] * 3, raw["player"]["max_hp"] * 2, turn)
            # The blindness began on this board or on the blind run of boards before it.
            onset = turn
            while "目が見えなくなってしまった！" not in rows[onset]["messages"]:
                onset = turns[turns.index(onset) - 1]
                self.assertTrue(rows[onset]["player"]["status"]["blind"], (turn, onset))
            self.assertTrue(any(m.endswith("閃光のブレスを吐いた。")
                                for m in rows[onset]["messages"]), (turn, onset))
        def potions(turn):
            return sum(item["count"] for item in rows[turn]["inventory"]
                       if CURE_CRITICAL in item["name"] or "体力回復の薬" in item["name"])
        self.assertEqual((potions(CURED[0]), potions(LAST_HEALING), potions(880426)), (13, 1, 0))

    def test_flash_blindness_at_high_hp_drinks_no_cure(self):
        answers = run(877017, 877691)
        answers.update(run(880383, 880451))
        for turn in CURED + (LAST_HEALING,):
            key, reason = answers[turn]
            self.assertFalse(key.startswith("q"), (turn, key, reason))
            self.assertIn(reason, SHORT, turn)
        # A hound beside the player is struck (owner 11-07, 「隣の敵は殴り」).
        self.assertEqual(answers[877182][1], SHORT_BLIND_MELEE_REASON)
        self.assertEqual(answers[877156][1], SHORT_BLIND_WAIT_REASON)

    def test_lower_hp_still_cures_the_flash_blindness(self):
        # DECLARED CONSTRUCTED: the first cure board with a third of max HP gone
        # (the owner's 「HP が減った時」, the 11-04 line): the cure is drunk.
        def hurt(raw):
            if raw["turn"] == CURED[0]:
                raw["player"]["hp"] = raw["player"]["max_hp"] * 2 // 3 - 1
        answers = run(877017, CURED[0], edit=hurt)
        key, reason = answers[CURED[0]]
        # Heavily hurt and blind, the HP recovery potion is the cure (owner 2026-11-04).
        self.assertEqual((key[:1], reason), ("q", "emergency:cure-status-healing"))

    def test_a_gas_trap_blindness_is_still_cured(self):
        # DECLARED CONSTRUCTED: the gas trap board of the death floor with one Cure
        # Critical Wounds in the pack (the arrival's row): a long blindness is cured.
        row = cure_row()
        row["count"] = 1
        def add(raw):
            if raw["turn"] >= GAS_TRAP:
                taken = {item["slot"] for item in raw["inventory"]}
                slot = next(chr(code) for code in range(ord("a"), ord("z") + 1)
                            if chr(code) not in taken)
                raw["inventory"].append(dict(copy.deepcopy(row), slot=slot))
        policy = new_policy(LANDING)
        answer = None
        for raw in boards(LANDING, GAS_TRAP):
            add(raw)
            key = decide(policy, raw)
            answer = (key, policy.last_reason)
            policy.confirm_key_posted(key)
        self.assertEqual(answer[1], "item:cure-critical")
        self.assertTrue(answer[0].startswith("q"), answer)


if __name__ == "__main__":
    unittest.main()
