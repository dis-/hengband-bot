"""n1-b life-391 (Magic-Eater Lv40, HP 556, Angband 80F) died 2026-11-13 18:54:35.

Recorded: tests/fixtures/n1b-391-death-1113.pkl.xz (tests/extract_n1b_391_death_1113_fixture.py):
for each decision 6399-6409 the response lines the live bot read and the policy checkpoint it
decided that board from (the live history from the town-arrival checkpoint).  Each pin restores
its board's checkpoint and decides through the public ``choose_key``.

The death.  The powerful detect-all of 6404 showed four awake uniques on the floor, 竜の
『ファフナー』 (race 712, 2750 HP) and 黄金竜『スマウグ』 (race 697, 2000 HP) among them, both
BR_FIRE, speed +10 (the player +13), known by telepathy alone, never in view.  The bot explored
on (each dragon alone is no T1 from contact, so the sensed leave of 2026-11-08 does not apply;
see the owner question of this branch).  On 6409 the step to (48, 48) put both within reach of a
breath at a grid beside the player (mspell-lite.cpp, ``_offset_spell_reach``): the next action's
p95 read 537 (BR_FIRE min(HP/3, 1600) through the player's fire resistance, rate (100+2)/3 = 34%:
916 * 34 / 100 = 311 and 666 * 34 / 100 = 226; mspell-damage-calculator.cpp, player-status-resist.cpp
calc_fire_damage_rate) against HP 533, so 3.1 即死 held, and the board explored on: the shared
ladder's 1-turn test in ``_emergency_item`` was asked only while ``hostiles`` (the hostiles in
view) was non-empty, and the awake detected dragons are in ``threat_tiers.engagement`` only.  Both
breathed before the next board (533 -> dead).

Owner 2026-11-09 B 「即死はテレポートで逃げる。」: now the 1-turn test reads the engagement on
every board, and 6409 reads the Teleportation scroll (14 carried).

Owner 2026-11-13 (「今のまま即死はテレポート」, and *Destruction* where no scroll can be read):
on the 即死 board without a Teleportation scroll, or blind, the ladder's *Destruction* counted
only the awake hostiles in view, so the two sensed dragons (12 and 15 cells by the game's
distance) never got it.  Now it counts the engagement.  DECLARED CONSTRUCTED variants of
6409: the scrolls taken out of the pack, or the player blind; the absorbed *Destruction* (87%)
answers.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import lzma
import pickle
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import threat_tiers
from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import game_distance
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-391-death-1113.pkl.xz"
FAFNER, SMAUG = 712, 697
TELEPORT_REASON = "emergency:teleport"
DESTRUCTION = ("mA3", "emergency:destruction:absorbed-power")


def _case():
    return pickle.loads(lzma.decompress(FIXTURE.read_bytes()))


CASE = _case()
SEGMENTS = {segment["decision"]["decision_sequence"]: segment for segment in CASE["segments"]}


def decide(sequence, change=lambda board: board):
    """(policy, board, key, reason) of the board as HEAD decides it from the live history;
    ``change`` makes a DECLARED CONSTRUCTED variant of the board."""
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoints"][sequence])
    with TemporaryDirectory() as scratch:
        _, boards = _consume_response_sequence(
            SEGMENTS[sequence]["lines"], policy, lambda _key: True, policy._monrace_knowledge,
            knowledge_ledger_path=Path(scratch) / "k.jsonl")
    board = change(policy.with_known_skill_exp(boards[-1]))
    key = str(policy.choose_key(board))
    return policy, board, key, policy.last_reason


def live(sequence):
    decision = SEGMENTS[sequence]["decision"]
    return decision["key"], decision["reason"]


def dragons(policy, board):
    return {monster.race_id: monster for monster in threat_tiers.engagement(policy, board)
            if monster.race_id in (FAFNER, SMAUG)}


class N1b391Death1113RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decided = {sequence: decide(sequence) for sequence in range(6405, 6410)}

    def test_recorded_scene(self):
        """6405-6409 explored; on 6409 the two dragons are awake, detected, out of view."""
        self.assertEqual([live(sequence)[1] for sequence in range(6405, 6410)], ["explore"] * 5)
        policy, board, _, _ = self.decided[6409]
        self.assertFalse(board.visible_monsters)
        seen = dragons(policy, board)
        self.assertEqual(sorted(seen), [SMAUG, FAFNER])
        for monster in seen.values():
            self.assertEqual((monster.perception, monster.asleep), ("detected", False))
            self.assertFalse(policy._may_project(board, monster.position, board.player.position))
            self.assertEqual(policy._offset_spell_reach(board, monster), (0, False))

    def test_death_board_reads_instant_death(self):
        """6409: the next action's p95 is the two resisted fire breaths, 311 + 226 = 537 >= 533."""
        policy, board, _, _ = self.decided[6409]
        self.assertEqual(board.player.hp, 533)
        result = threat_tiers.instant_death(policy, board)
        self.assertTrue(result.next_action)
        self.assertEqual(result.next_action_p95, 537)
        rows = {row["race_id"]: row for row in policy.threat_prediction(
            board, list(dragons(policy, board).values()), 1)["monsters"]}
        self.assertEqual(rows[FAFNER]["ranged_prediction"], 2750 // 3 * 34 // 100)
        self.assertEqual(rows[SMAUG]["ranged_prediction"], 2000 // 3 * 34 // 100)

    def test_death_board_teleports(self):
        """6409: owner 2026-11-09 B, the Teleportation scroll (live: the explore step)."""
        self.assertEqual(live(6409), ("2", "explore"))
        _, board, key, reason = self.decided[6409]
        scroll = next(item for item in board.inventory if item.is_teleport_scroll)
        self.assertEqual((key, reason), ("r" + scroll.slot, TELEPORT_REASON))

    def test_death_board_without_a_scroll_destroys(self):
        """6409 with no Teleportation scroll in the pack (DECLARED CONSTRUCTED): the dragons,
        sensed only, are in the guaranteed radius (12 and 15 cells by the game's distance)."""
        policy, board, key, reason = decide(6409, lambda board: replace(board, inventory=[
            item for item in board.inventory if not item.is_teleport_scroll]))
        self.assertTrue(threat_tiers.instant_death(policy, board).next_action)
        here = board.player.position
        self.assertEqual(sorted(game_distance(here, monster.position)
                                for monster in dragons(policy, board).values()), [12, 15])
        self.assertEqual((key, reason), DESTRUCTION)

    def test_blind_death_board_destroys(self):
        """6409 blind (DECLARED CONSTRUCTED): no scroll can be read; the absorbed power is cast
        blind (owner 2026-11-08 「盲目でも使う」)."""
        _, _, key, reason = decide(6409, lambda board: replace(
            board, player=replace(board.player, blind=True)))
        self.assertEqual((key, reason), DESTRUCTION)

    def test_boards_before_the_reach_explore_on(self):
        """6405-6408: no breath reaches before the player's next action (each dragon one action
        a turn, no line and no grid beside the player in reach): no 即死, the explore stands."""
        for sequence in range(6405, 6409):
            with self.subTest(sequence=sequence):
                policy, board, key, reason = self.decided[sequence]
                self.assertFalse(threat_tiers.instant_death(policy, board).holds)
                self.assertEqual((key, reason), live(sequence))


if __name__ == "__main__":
    unittest.main()
