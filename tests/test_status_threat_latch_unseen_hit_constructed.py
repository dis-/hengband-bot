"""Pins: the pink-horror flee is consistent; an unseen hit survives its cure.

User report 2026-10-02 (verbatim): 「敵の眼の前で攻撃もせずにうろうろしていた
こと。ピンクホラーへの対処が逃げ一択ではなかったこと。逃げること自体は正しい。」

Both scenes are Castle 20F (dungeon 12) of 2026-10-02 with the same character
(scythe + sling, no rConf).  NO BOARD of either window survives: the capture
rings of 13:12 start at turn 3644500 and the live state log was truncated by
the 15:0x relaunch.  What remains is printed rows only:

* 13:10:57-13:11:05 (decision rows: the decision tail of the 13:16:26
  no-key-exhausted incident capture; threat_prediction of each row): after
  ``emergency:quaff-speed`` (5361) the hasted player's 3-turn reach of the
  ピンク・ホラー (race 242, CONFUSE bite) is 3 actions, so the status-threat
  rung fires at path distance 3 and is silent at 4:
  5368 '6' status-threat:retreat (pd 3) / 5369 fire-target /
  5370 '6' status-threat:retreat (pd 3) / 5371 'fm*t5<esc>' ranged:fire-target
  (pd 4) / ... / 5391-5392 ranged:fire-target (pd 4) / 5393 '6'
  status-threat:retreat (pd 3).
* 13:06:08-14 (ownership-claims.jsonl rows, reasons and positions only):
  4051 emergency:cure-critical, 4052 explore, 4056/4060/4062/4063/4067
  emergency:cure-critical each followed by explore/melee/probe, 4068-4080
  probe/explore while シャドウ・ハウンド breathed darkness from the dark
  (user report: 「何かが暗黒のブレスを吐いた」).

DECLARED CONSTRUCTED: the substrate is the recorded Castle 20F board of
decision 5613 (capture autorecover-20261002-131232-loop-detected, frozen in
two-cell-oscillation-20261002.jsonl.gz; player (49,77) in an open room), with
its monster lists replaced.  The ピンク・ホラー is the recorded monster of
board 5638 (same capture), moved to the path distances of the rows above; the
player's speed is set to the hasted 120 of 5362-5393.  The unseen-hit boards
carry the blindness of a darkness breath and the cure's recovery message.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge

import test_two_cell_oscillation_recorded as recorded
from test_esp_threat_rest_recorded import EDIT, _policy

SUBSTRATE = 5613  # recorded board: player (49,77), open room
HORROR_BOARD = 5638  # recorded board with a visible ピンク・ホラー
PINK_HORROR = 242
HASTED = 120
NEAR = Position(49, 74)  # path distance 3 from (49,77)
DIRECTIONS = {
    "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
    "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
}


class _Substrate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        boundaries, _table, lines = recorded._load()
        cls.ends = {int(k): v for k, v in boundaries["b_board_end"].items()}
        cls.lines = lines["b"]
        with gzip.open(recorded.CASTLE_FIXTURE, "rt", encoding="utf-8") as stream:
            cls.knowledge = json.loads(stream.readline())
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        horror_board = parse_snapshot(
            json.loads(cls.lines[cls.ends[HORROR_BOARD]]), cls.monrace
        )
        cls.horror = next(
            m for m in horror_board.visible_monsters if m.race_id == PINK_HORROR
        )

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.policy = _policy(Path(self._tmp.name), self.monrace)
        self.policy._character_calibration_path.write_bytes(
            recorded.CALIBRATION.read_bytes()
        )
        self.policy._crossarea_fundraising_enforced = True  # live argv
        self.policy.consume_skill_knowledge(self.knowledge)  # declared wall
        _decoded, snapshots = _consume_response_sequence(
            self.lines[: self.ends[SUBSTRATE] + 1], self.policy,
            lambda _key: True, self.monrace,
            knowledge_ledger_path=Path(self._tmp.name) / "knowledge.jsonl",
        )
        self.board = snapshots[-1]
        self.assertEqual(self.board.floor_key, recorded.CASTLE_20F)
        self.assertEqual(self.board.player.position, Position(49, 77))
        # Warm-up (key not asserted): one decision on the substrate with its
        # monsters removed gives the fresh process its HP/position baseline.
        self._choose(replace(
            self.board, visible_monsters=[], detected_monsters=[], messages=[],
            turn=self.board.turn - 1,
        ))

    def _choose(self, board):
        key = self.policy.choose_key(board)
        self.policy.confirm_key_posted(key)
        return key, self.policy.last_reason


class StatusThreatLatchConstructedTest(_Substrate):
    """Item 4: a status threat that triggered the escape is not fired at."""

    def _hasted_with_horror(self, player_at, *, turn_offset):
        horror = replace(
            self.horror, position=NEAR, distance=NEAR.distance_to(player_at)
        )
        return replace(
            self.board,
            player=replace(self.board.player, position=player_at, speed=HASTED),
            visible_monsters=[horror],
            detected_monsters=[],
            messages=[],
            turn=self.board.turn + turn_offset,
        )

    def test_retreat_then_one_step_further_keeps_escaping(self):
        near = self._hasted_with_horror(self.board.player.position, turn_offset=0)
        self.assertNotIn("resist_conf", near.player.abilities)
        self.assertEqual(self.policy._monster_path_distance(near, NEAR), 3)
        key, reason = self._choose(near)
        self.assertEqual(reason, "status-threat:retreat")  # live 5368/5370/5393
        dy, dx = DIRECTIONS[key]
        here = near.player.position
        stepped = Position(here.y + dy, here.x + dx)
        further = self._hasted_with_horror(stepped, turn_offset=10)
        self.assertEqual(self.policy._monster_path_distance(further, NEAR), 4)
        key, reason = self._choose(further)
        # Live 5371: 'fm*t5\x1b' ranged:fire-target at path distance 4.
        self.assertTrue(reason.startswith("status-threat:"), (key, reason))

    def test_a_horror_not_yet_fled_from_is_still_shot_at_beyond_its_reach(self):
        # 「逃げること自体は正しい」 is about the threat within reach; beyond
        # its 3-turn reach the ordinary ranged rung still owns the decision.
        further = self._hasted_with_horror(Position(49, 78), turn_offset=0)
        self.assertEqual(self.policy._monster_path_distance(further, NEAR), 4)
        key, reason = self._choose(further)
        self.assertTrue(reason.startswith("ranged:fire"), (key, reason))


class UnseenHitAfterEmergencyCureConstructedTest(_Substrate):
    """Item 3: the unseen breath is not forgotten because the cure came first."""

    def test_unseen_breath_then_cure_retreats_instead_of_exploring(self):
        player = self.board.player
        breathed = replace(
            self.board,
            player=replace(player, blind=True, hp=player.max_hp - 90),
            visible_monsters=[], detected_monsters=[],
            messages=["何かが暗黒のブレスを吐いた。", "目が見えなくなってしまった！"],
            turn=self.board.turn + 5,
        )
        _key, reason = self._choose(breathed)
        self.assertEqual(reason, "emergency:cure-critical")  # live 4051
        cured = replace(
            self.board,
            player=replace(player, hp=player.max_hp - 40),
            visible_monsters=[], detected_monsters=[],
            messages=["やっと目が見えるようになった。"],
            turn=self.board.turn + 15,
        )
        key, reason = self._choose(cured)
        # Live 4052: '3' explore, as if the floor were empty.
        self.assertEqual(reason, "unseen:reverse-choke", key)


if __name__ == "__main__":
    unittest.main()
