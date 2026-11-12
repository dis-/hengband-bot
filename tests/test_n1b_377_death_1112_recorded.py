"""n1-b life-377 (Magic-Eater Lv46, HP 666, Angband 80F) died 2026-11-12 13:46:53.

Recorded: tests/fixtures/n1b-377-death-1112.pkl.xz (tests/extract_n1b_377_death_1112_fixture.py):
for each decision 7965-7976 the response lines the live bot read and the policy checkpoint it
decided that board from (the live history up to it, replayed through the live response path
from the town-arrival checkpoint and matching every recorded key and reason).  Each pin
restores its board's checkpoint and decides through the public ``choose_key``.

The death.  世紀末覇者『ラオウ』 (race 1018, T1 alone, known by telepathy 8-10 cells off) was
approached for *Destruction* (owner 2026-11-10 「積極的に*破壊*で消しにいく」); from 7965 the
sensed leave's *Destruction* (absorbed, 97%) was due on every board until the stun, but:

1. 7965-7972, 7974-7975: the dug pocket answered (``anaguma:dig/step/hold``, ``melee:anaguma``;
   the floor-avoidance layer, above the sensed leave in the combat layer).  Owner 2026-11-10
   穴熊 「穴を捨てる線は今の基準のまま」「高威力攻撃を持つ個体は通常の生存ルーチンで対応する」:
   now the sensed leave answers where the pocket would (ladder_floor_avoidance).
2. 7973: the THREAT power (me_powers ``unbeatable-in-range``, the emergency layer) sent the
   summoned ボダック away.  Owner 2026-11-09 B 「即死でない強敵は *破壊* 優先」: now the leave's
   *Destruction* is asked directly above it (threat_tiers ``sensed_t1_destruction_key``).
3. 7975 a plasma bolt stunned the player (slight, stun_rank 1): no *Destruction* while not
   clear-headed; 7976 the absorbed Teleport Away (97% shown, 87% stunned: cmd-magiceat.cpp:485,
   player-stun.cpp:135-153) failed, though a Teleportation scroll (no penalty at this stun,
   player-stun.cpp:162-178) was in the pack.  Now a stunned THREAT power gives way to the
   surer scroll (me_powers ``_stunned_scroll_first``).
4. 混沌の王族 (race 737) alone reads T2 from contact, not T1: four Healing potions win (supply margin
   101, the game's spell choice and failure rate of main cf3ae5189f) and it is a reward race (DROP_4D2); the sensed leave reads T1 alone, as
   the owner's rule of 2026-11-08 says.  Not changed (pinned as it reads).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import lzma
import pickle
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_powers, threat_tiers
from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-377-death-1112.pkl.xz"
CHAOS_LORD, RAOH = 737, 1018
DESTRUCTION = ("mA3", "emergency:destruction:absorbed-power")
SCROLL_LEAVE = ("re", "sensed-t1:teleport")
TELEPORT_AWAY = ("mCn7", "me-power:unbeatable-in-range:teleport-away")


def _case():
    return pickle.loads(lzma.decompress(FIXTURE.read_bytes()))


CASE = _case()
SEGMENTS = {segment["decision"]["decision_sequence"]: segment for segment in CASE["segments"]}


def decide(sequence):
    """(policy, board, key, reason) of the board as HEAD decides it from the live history."""
    policy = restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoints"][sequence])
    with TemporaryDirectory() as scratch:
        _, boards = _consume_response_sequence(
            SEGMENTS[sequence]["lines"], policy, lambda _key: True, policy._monrace_knowledge,
            knowledge_ledger_path=Path(scratch) / "k.jsonl")
    board = policy.with_known_skill_exp(boards[-1])
    key = str(policy.choose_key(board))
    return policy, board, key, policy.last_reason


def live(sequence):
    decision = SEGMENTS[sequence]["decision"]
    return decision["key"], decision["reason"]


def shown(board, race):
    return next(monster for monster in (*board.visible_monsters, *board.detected_monsters)
                if monster.race_id == race)


class N1b377Death1112RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decided = {sequence: decide(sequence) for sequence in sorted(SEGMENTS)}

    def test_recorded_scene(self):
        self.assertEqual([live(sequence)[1] for sequence in range(7965, 7977)], [
            "anaguma:dig", "anaguma:step", "anaguma:dig", "anaguma:step",
            "anaguma:hold", "anaguma:hold", "anaguma:hold", "anaguma:hold",
            TELEPORT_AWAY[1], "melee:anaguma", "melee:anaguma", TELEPORT_AWAY[1]])
        policy, board, _, _ = self.decided[7965]
        raoh = shown(board, RAOH)
        self.assertEqual((raoh.perception, raoh.asleep, raoh.distance), ("detected", False, 10))
        self.assertTrue(threat_tiers.inside_sensing(policy, board, raoh))
        self.assertEqual([monster.race_id for monster in threat_tiers._sensed_strong(policy, board)[1]],
                         [RAOH])
        stunned = [self.decided[sequence][1].player.stun_rank for sequence in range(7973, 7977)]
        self.assertEqual(stunned, [0, 0, 1, 1])

    def test_the_first_pocket_board_destroys(self):
        """7965: *Destruction* (owner 2026-11-09 B, 2026-11-10), not the dig."""
        self.assertEqual(live(7965), ("ai2", "anaguma:dig"))
        self.assertEqual(self.decided[7965][2:], DESTRUCTION)

    def test_no_pocket_answer_while_the_t1_is_sensed(self):
        """7965-7976: neither the pocket's dig, step, hold nor its blow answers."""
        for sequence in range(7965, 7977):
            with self.subTest(sequence=sequence):
                reason = self.decided[sequence][3]
                self.assertFalse(reason.startswith("anaguma:") or reason == "melee:anaguma", reason)
        for sequence in range(7965, 7975):
            with self.subTest(sequence=sequence):
                self.assertEqual(self.decided[sequence][2:], DESTRUCTION)

    def test_stunned_pocket_board_reads_the_sensed_leave(self):
        """7975: stunned, *Destruction* is out (no clear head); the pocket's blow was the live
        answer, the sensed leave's Teleportation scroll is HEAD's (ladder_floor_avoidance)."""
        self.assertEqual(live(7975), ("7", "melee:anaguma"))
        self.assertEqual(self.decided[7975][2:], SCROLL_LEAVE)

    def test_summoned_bodak_is_not_sent_away_before_destruction(self):
        """7973: the THREAT power on the summoned ボダック was live; *Destruction* now."""
        policy, board, key, reason = self.decided[7973]
        self.assertEqual(live(7973), TELEPORT_AWAY)
        self.assertEqual([(monster.race_id, monster.distance) for monster in board.visible_monsters],
                         [(566, 1)])
        self.assertEqual((key, reason), DESTRUCTION)

    def test_stunned_teleport_away_gives_way_to_the_scroll(self):
        """7976: the absorbed Teleport Away at 87% stunned against the scroll's 100%."""
        policy, board, key, reason = self.decided[7976]
        self.assertEqual(live(7976), TELEPORT_AWAY)
        self.assertEqual((board.player.stunned, board.player.stun_rank), (True, 1))
        self.assertEqual(me_powers.stunned_success(policy, board, ("rod", 13)), 87)
        self.assertEqual((key, reason), SCROLL_LEAVE)

    def test_chaos_lord_alone_reads_t2(self):
        """5: the reading as it stands (not changed): T2 by four Healing potions,
        a reward race, its summons a worsening (the leave_due / summoner rules, not T1)."""
        policy, board, _, _ = self.decided[7974]
        result = threat_tiers.tiered(policy, board, [shown(board, CHAOS_LORD)], contact=True)
        self.assertEqual(result.tier, threat_tiers.T2)
        self.assertEqual(result.supply_plan.heals, (300, 300, 300, 300))
        self.assertGreater(result.supply_margin, 0)
        entry = next(iter(result.per_monster.values()))
        self.assertEqual((entry.selected, entry.worsens_with_time), (("reward",), ("summon",)))



if __name__ == "__main__":
    unittest.main()
