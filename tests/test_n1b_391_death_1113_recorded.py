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
6409: the scrolls taken out of the pack (the absorbed *Destruction*, 87%, answers), or the
player blind (owner 2026-11-13 「成功率の高い方を先に」: the absorbed Teleportation, 92%, unless
*Destruction* is as sure).

Owner 2026-11-13 (this death's question, answer 「まとめて判定する」): awake sensed strong
monsters are judged together; T1 together, they are the sensed T1 (threat_tiers
``_sensed_strong``).  Each dragon is T2 alone from contact, the pair T1.  From 6407 both are
inside their sensing radius (vision 20): 6407 walks toward the sure radius
(``sensed-t1:approach-destruction``, live: the explore step, the same key), 6408 has both inside
it (9 and 13 cells) and uses the absorbed *Destruction*.  6405: the dragons are outside their
sensing radius and パーサーナックス (T1 alone, 31 cells off) is the sensed T1 already, with no known
way toward it (unchanged); 6406: only ファフナー is sensing, no group.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import lzma
import pickle
import unittest
from unittest import mock
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import deep_teleport, destruction_use, me_capability, me_power_success, threat_tiers
from hengbot.me_absorbed_substitutes import TELEPORTATION
from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import game_distance
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-391-death-1113.pkl.xz"
FAFNER, SMAUG = 712, 697
TELEPORT_REASON = "emergency:teleport"
APPROACH = "sensed-t1:approach-destruction"
DESTRUCTION = ("mA3", "emergency:destruction:absorbed-power")
BLIND_TELEPORT = ("mAe", "emergency:teleport:absorbed-power")


def blind(board):
    return replace(board, player=replace(board.player, blind=True))


def _case():
    return pickle.loads(lzma.decompress(FIXTURE.read_bytes()))


CASE = _case()
SEGMENTS = {segment["decision"]["decision_sequence"]: segment for segment in CASE["segments"]}


def consumed(sequence):
    """(policy, board) of the board read from the live history, not yet decided."""
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoints"][sequence])
    with TemporaryDirectory() as scratch:
        _, boards = _consume_response_sequence(
            SEGMENTS[sequence]["lines"], policy, lambda _key: True, policy._monrace_knowledge,
            knowledge_ledger_path=Path(scratch) / "k.jsonl")
    return policy, policy.with_known_skill_exp(boards[-1])


def decide(sequence, change=lambda board: board):
    """(policy, board, key, reason) of the board as HEAD decides it from the live history;
    ``change`` makes a DECLARED CONSTRUCTED variant of the board."""
    policy, board = consumed(sequence)
    board = change(board)
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
        """6409: owner 2026-11-09 B, the Teleportation scroll (live: the explore step).
        DECLARED CONSTRUCTED: the 50F+ rule of 2026-11-14 walled off (deep_teleport.allows)."""
        self.assertEqual(live(6409), ("2", "explore"))
        with mock.patch.object(deep_teleport, "allows", lambda policy, snapshot: True):
            _, board, key, reason = decide(6409)
        scroll = next(item for item in board.inventory if item.is_teleport_scroll)
        self.assertEqual((key, reason), ("r" + scroll.slot, TELEPORT_REASON))

    def test_death_board_destroys_under_the_50f_teleport_rule(self):
        """6409 as recorded, owner 2026-11-14 「50F以降のテレポートの条件を厳しくする。…射線の通って
        いる敵の合計予測被害95%が現在HPを上回るとき=即死のときのみ。当てはまらない時は破壊または
        近寄って破壊を試みる。」: neither dragon has a line of fire to the player on this board
        (their breaths of the 即死 test come after a step), so the sum of those with one is 0 and
        *Destruction* (87%) is used in the scroll's place."""
        policy, board, key, reason = self.decided[6409]
        self.assertTrue(threat_tiers.instant_death(policy, board).next_action)
        self.assertEqual(deep_teleport.fire_p95(policy, board), 0)
        self.assertEqual((key, reason), (DESTRUCTION[0], "emergency:destruction"
                                         + deep_teleport.DESTRUCTION_SUFFIX + ":absorbed-power"))

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

    def test_blind_death_board_reads_the_surer_power(self):
        """6409 blind (DECLARED CONSTRUCTED): no scroll can be read.  Owner 2026-11-13 「成功率の
        高い方を先に」: the absorbed Teleportation (92% shown) before *Destruction* (87%).
        DECLARED CONSTRUCTED too: the 50F+ rule of 2026-11-14 walled off (deep_teleport.allows);
        under it the cast gives way to *Destruction* (test_death_board_destroys_under_...)."""
        with mock.patch.object(deep_teleport, "allows", lambda policy, snapshot: True):
            policy, board, key, reason = decide(6409, blind)
        self.assertEqual(threat_tiers.blind_teleport_success(policy, board), 92)
        self.assertEqual(destruction_use.success(policy, board), 87)
        self.assertEqual((key, reason), BLIND_TELEPORT)

    def test_blind_death_board_destroys_on_a_tie(self):
        """6409 blind with the Teleportation row shown at *Destruction*'s 87% (DECLARED
        CONSTRUCTED: the last displayed list's failure 13 for 8): on a tie *Destruction* first."""
        policy, board = consumed(6409)
        row = me_capability.observed_row(policy, *TELEPORTATION)
        row.update(fail=13, success=87)
        board = blind(board)
        # The constructed row is the list shown on this board (me_power_success reads a shown
        # rate on the inputs it was shown on, else the game's formula).
        me_power_success.observe_list_board(policy, TELEPORTATION[0], board)
        self.assertEqual(threat_tiers.blind_teleport_success(policy, board), 87)
        self.assertEqual((str(policy.choose_key(board)), policy.last_reason), DESTRUCTION)

    def test_boards_before_the_reach_read_no_instant_death(self):
        """6405-6408: no breath reaches before the player's next action (each dragon one action
        a turn, no line and no grid beside the player in reach): no 即死."""
        for sequence in range(6405, 6409):
            with self.subTest(sequence=sequence):
                policy, board, _, _ = self.decided[sequence]
                self.assertFalse(threat_tiers.instant_death(policy, board).holds)

    def test_each_dragon_is_t2_alone_and_the_pair_t1(self):
        """6407-6409: from contact each is T2 alone, the two together cannot be beaten."""
        for sequence in range(6407, 6410):
            with self.subTest(sequence=sequence):
                policy, board, _, _ = self.decided[sequence]
                pair = dragons(policy, board)
                hp = board.player.hp
                for monster in pair.values():
                    self.assertTrue(threat_tiers.inside_sensing(policy, board, monster))
                    self.assertEqual(threat_tiers.tiered(
                        policy, board, [monster], contact=True).tier, threat_tiers.T2)
                self.assertTrue(threat_tiers.cannot_win(threat_tiers.tiered(
                    policy, board, list(pair.values()), contact=True), hp))
                self.assertEqual(sorted(monster.race_id for monster
                                        in threat_tiers._sensed_strong(policy, board)[1]),
                                 [SMAUG, FAFNER])

    def test_the_pair_is_approached_then_destroyed(self):
        """Owner 2026-11-13 「まとめて判定する」 with 2026-11-10 「積極的に*破壊*で消しにいく」:
        6407 walks toward the sure radius, 6408 (ファフナー 9, スマウグ 13 cells) destroys."""
        self.assertEqual(live(6407), ("2", "explore"))
        self.assertEqual(self.decided[6407][3], APPROACH)
        self.assertEqual(live(6408), ("1", "explore"))
        self.assertEqual(self.decided[6408][2:], DESTRUCTION)

    def test_boards_without_a_sensed_pair_are_unchanged(self):
        """6405 (the dragons outside their sensing radius) and 6406 (ファフナー alone sensing,
        T2): no group, the recorded explore stands."""
        for sequence in (6405, 6406):
            with self.subTest(sequence=sequence):
                self.assertEqual(self.decided[sequence][2:], live(sequence))

if __name__ == "__main__":
    unittest.main()
