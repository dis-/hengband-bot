"""The unseen retreat armed by blind hits yields once sight shows the hostiles (n1-c life-195, 2026-11-11).

n1-c life-195 (Magic-Eater Lv 37, zombie), オークの洞窟23階 (floor (3, 23, 0)), stopped with
``loop-detected`` at 17:26:09: the light hounds (ライト・ハウンド, race 271, BR_LITE) blinded it
again and again.  Each blindness is randint1(5) + 2 ticks and a light breath on a player who is
already blind only prints 「何かで攻撃された！」 (effect-player-resist-hurt.cpp:406-412), so the
owner's short-blindness wait (2026-11-10 G1 「飲まずに戦うか待つ」) ended every time.  But a breath
on a blind board (「何かが何かのブレスを吐いた。」「何かで攻撃された！」, decision 20345) had armed
the unseen-attacker retreat on the sighted board after it (20346, no hostile in view), and the
armed retreat took every later sighted board for a ``unseen:reverse-choke`` step with the hounds
in view, back and forth between (12, 176) and (16, 176), never a shot, until the loop detector.

The retreat is for attackers the player cannot see (``_unseen_retreat_key``); a hit on a sighted
board with a visible monster never arms it.  The fix: a retreat that only blind hits armed is
cleared on a sighted board that shows a hostile, and the combat ladder answers.

Recorded (tests/fixtures/n1c-195-short-blind-1111.json.gz, see
tests/extract_n1c_195_short_blind_1111_fixture.py): the boards of turns 4268823-4269495
(decisions 20340-20441), decided in order by one policy's public ``choose_key`` from a fresh
process.  DECLARED RECONSTRUCTED: the skill reply (the last skill-exp row before the span) and
the absorbed devices (the stop's record).  The replay keeps the live answers through the arming
(20346; the first three boards are the fresh process's
new-floor detection) and diverges first on 20347, the first sighted board with a hostile in view.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.status_cure import SHORT_BLIND_WAIT_REASON
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-195-short-blind-1111.json.gz"
LIGHT_HOUND = 271
RETREAT = "unseen:reverse-choke"
ARMING_HIT = 4268869   # 20345: blind, 「何かで攻撃された！」
ARMED = 4268877        # 20346: sight back, nothing in view, the retreat armed
FIRST_SIGHTED = 4268882  # 20347: sight, a hostile in view
# The fresh process's first boards on the floor cast its new-floor detection (not done live
# on these boards, the process had cast it on arrival); the comparison starts after them.
WARMUP_LAST = 4268842


class N1c195ShortBlindRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.live = {row["turn"]: (row["key"], row["reason"]) for row in cls.data["decisions"]
                    if row["reason"] != "loop-detected"}

    def board(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.monrace)

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.board(self.data["boards"][0])
        policy.prime(first)
        skill = self.data["skill"]
        # DECLARED RECONSTRUCTED (module docstring): the skill reply and the absorbed devices.
        policy.consume_skill_knowledge(dict(copy.deepcopy(skill), turn=first.turn,
                                            player=dict(skill["player"], level=first.player.level)))
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(self.data["absorbed"]))
        terrain = self.data["terrain"]
        for name in ("known", "marked", "floor", "wall", "door", "rubble"):
            getattr(policy, f"_remembered_{name}_t").update(tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
        return policy

    def replay(self, last):
        policy, rows = self.policy(), {}
        for raw in self.data["boards"]:
            if raw["turn"] > last:
                break
            board = self.board(raw)
            key = str(policy.choose_key(policy.with_known_skill_exp(board)))
            rows[raw["turn"]] = (key, policy.last_reason, board)
            policy.confirm_key_posted(key)
        return policy, rows

    # ------------------------------------------------------------ the record

    def test_the_record_is_the_incident(self):
        boards = {raw["turn"]: self.board(raw) for raw in self.data["boards"]}
        hit = boards[ARMING_HIT]
        self.assertTrue(hit.player.blind)
        self.assertIn("何かで攻撃された！", hit.messages)
        self.assertFalse(boards[ARMED].player.blind)
        self.assertEqual(boards[ARMED].visible_monsters, [])
        self.assertEqual(self.live[ARMED][1], RETREAT)
        sighted = [turn for turn, board in boards.items()
                   if turn >= FIRST_SIGHTED and not board.player.blind
                   and any(not m.pet and not m.friendly for m in board.visible_monsters)]
        retreats = [turn for turn in sighted if self.live.get(turn, ("", ""))[1] == RETREAT]
        self.assertGreaterEqual(len(retreats), 8, sighted)
        self.assertTrue(any(m.race_id == LIGHT_HOUND for turn in sighted
                            for m in boards[turn].visible_monsters))
        waits = [turn for turn in boards if self.live.get(turn, ("", ""))[1] == SHORT_BLIND_WAIT_REASON]
        self.assertTrue(all(boards[turn].player.blind for turn in waits))
        # Re-blinded each time by a flash breath after sight came back.
        onsets = [board for board in boards.values()
                  if "目が見えなくなってしまった！" in board.messages]
        self.assertGreaterEqual(len(onsets), 8)
        self.assertTrue(all(any(m.endswith("閃光のブレスを吐いた。") for m in board.messages)
                            for board in onsets))

    # ------------------------------------------------------------ the pins

    def test_the_replay_keeps_the_live_answers_through_the_arming(self):
        _policy, rows = self.replay(ARMED)
        compared = [turn for turn in rows if turn > WARMUP_LAST]
        self.assertEqual({turn: rows[turn][:2] for turn in compared},
                         {turn: self.live[turn] for turn in compared})

    def test_a_retreat_armed_by_blind_hits_yields_to_the_hostiles_in_view(self):
        policy, rows = self.replay(self.data["boards"][-1]["turn"])
        for turn, (key, reason, board) in rows.items():
            if turn < FIRST_SIGHTED or board.player.blind:
                continue
            if any(not m.pet and not m.friendly for m in board.visible_monsters):
                self.assertNotEqual(reason, RETREAT, (turn, key, reason))
        self.assertNotEqual(rows[FIRST_SIGHTED][1], RETREAT)
        self.assertEqual(self.live[FIRST_SIGHTED][1], RETREAT)
        # The short blindness is still waited out (owner 2026-11-10 G1).
        blind_waits = [row for row in rows.values() if row[2].player.blind]
        self.assertTrue(blind_waits)
        self.assertTrue(all(row[1] == SHORT_BLIND_WAIT_REASON for row in blind_waits
                            if not any(m.distance <= 1 for m in row[2].visible_monsters)),
                        [(row[0], row[1]) for row in blind_waits])

    def test_a_retreat_armed_by_a_sighted_hit_still_walks(self):
        """A hit on a sighted board with nothing in view (an attacker the player really cannot
        see) arms the retreat as before; a later hostile in view does not clear it unless it is
        adjacent or named (``_unseen_retreat_key``).  DECLARED CONSTRUCTED: the arming board's
        blindness taken off the pending hit."""
        policy, _rows = self.replay(ARMED)
        self.assertEqual(policy._unseen_retreat_floor, (3, 23, 0))
        self.assertTrue(policy._unseen_retreat_blind_only)
        policy._unseen_retreat_blind_only = False  # DECLARED CONSTRUCTED
        raw = next(raw for raw in self.data["boards"] if raw["turn"] == FIRST_SIGHTED)
        board = self.board(raw)
        key = str(policy.choose_key(policy.with_known_skill_exp(board)))
        self.assertEqual((key, policy.last_reason), self.live[FIRST_SIGHTED])


if __name__ == "__main__":
    unittest.main()
