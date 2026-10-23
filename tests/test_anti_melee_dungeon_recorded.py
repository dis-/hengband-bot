"""Pins the 2026-10-23 death in the Anti-melee cave and its controls.

Live 2026-10-23 21:23 (Linux soak c4-a life-014, Lv40 Zombie Warrior): after
five Angband dives without saved-depth progress the no-depth-progress valve
switched the recall target to dungeon 17, the Anti-melee cave (flag NO_MELEE,
recall depth 40), the deepest entered dungeon below Angband's 49.  In that
dungeon the game refuses every melee attack (cmd-attack.cpp:
「なぜか攻撃することができない。」), yet the bot posted ``melee`` about 80
times in its last 43 seconds and died.

The fixture holds three raw protocol-3 boards from that capture (state rows
at turns 8823126, 8823394 and 8823592, Anti-melee cave 45F); each was
recorded with key ``6`` / ``1`` / ``6``, reason ``melee``.  The policy checkpoint is
absent: DECLARED CONSTRUCTED, the protocol-3 skill-exp cache is set to the
captured level (40).  The destination-choice board is DECLARED CONSTRUCTED:
the recorded board's own progress block (entered dungeons and their recall
depths) is asked the no-depth-progress valve's question with the live blocked
depth 49.  The controls are DECLARED CONSTRUCTED by removing only the
NO_MELEE flag from the loaded dungeon knowledge.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import dataclasses
import gzip
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _consume_response_sequence
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS, WAIT_KEY
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "anti-melee-death-20261023.jsonl.gz"
FIXTURE_SHA256 = "3942d87df7f347dda0ac61fc480d76ddc501e9056e25c6d841fc87c0b2cf2155"
ANTI_MELEE_CAVE = 17
RECORDED = (
    (8823126, "6"),
    (8823394, "1"),
    (8823592, "6"),
)
BLOCKED_ANGBAND_DEPTH = 49


class AntiMeleeDungeonRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == len(RECORDED)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def _board(self, line, *, melee_allowed=False):
        directory = Path(self._directory.name)
        policy = _policy(directory, self.monrace)
        if melee_allowed:
            knowledge = dict(self.dungeons)
            info = knowledge[ANTI_MELEE_CAVE]
            knowledge[ANTI_MELEE_CAVE] = dataclasses.replace(
                info, flags=info.flags - {"NO_MELEE"}
            )
            policy._dungeon_knowledge = knowledge
        policy._skill_exp_cache = (0, 0, 40, None)
        _decoded, snapshots = _consume_response_sequence(
            [line],
            policy,
            lambda _key: True,
            self.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        self.assertEqual(len(snapshots), 1)
        return policy, snapshots[-1]

    def setUp(self):
        self._directory = TemporaryDirectory()

    def tearDown(self):
        self._directory.cleanup()

    def _attacked_cells(self, board):
        here = board.player.position
        return {
            DIRECTION_KEYS[(m.position.y - here.y, m.position.x - here.x)]
            for m in board.visible_monsters
            if m.position.distance_to(here) == 1
        }

    def test_recorded_boards_are_in_the_anti_melee_cave(self):
        self.assertIn("NO_MELEE", self.dungeons[ANTI_MELEE_CAVE].flags)
        for line, (turn, _key) in zip(self.lines, RECORDED):
            with self.subTest(turn=turn):
                _policy_instance, board = self._board(line)
                self.assertEqual(board.turn, turn)
                self.assertEqual(board.floor_key[:2], (ANTI_MELEE_CAVE, 45))
                self.assertEqual(board.player.level, 40)
                self.assertTrue(self._attacked_cells(board))

    def test_recorded_boards_do_not_melee_where_the_dungeon_forbids_it(self):
        # Was the recorded key / ``melee`` on every board.
        for line, (turn, _key) in zip(self.lines, RECORDED):
            with self.subTest(turn=turn):
                policy, board = self._board(line)
                key = policy.choose_key(board)
                self.assertNotEqual(policy.last_reason, "melee")
                self.assertNotIn(key, self._attacked_cells(board))

    def test_control_recorded_boards_melee_when_the_dungeon_allows_it(self):
        for line, (turn, recorded_key) in zip(self.lines, RECORDED):
            with self.subTest(turn=turn):
                policy, board = self._board(line, melee_allowed=True)
                key = policy.choose_key(board)
                self.assertEqual((key, policy.last_reason), (recorded_key, "melee"))

    def test_no_depth_progress_valve_never_picks_the_anti_melee_cave(self):
        policy, board = self._board(self.lines[0])
        self.assertIn(ANTI_MELEE_CAVE, board.entered_dungeon_ids)
        # Was 17 (recall depth 45, the deepest entered landing below 49).
        picked = policy._pick_alternate_dungeon(
            board,
            max_entry_depth=BLOCKED_ANGBAND_DEPTH - 1,
            prefer_deepest=True,
        )
        self.assertIsNotNone(picked)
        self.assertNotEqual(picked, ANTI_MELEE_CAVE)
        self.assertNotIn("NO_MELEE", self.dungeons[picked].flags)

    def test_control_valve_picks_the_same_dungeon_without_the_flag(self):
        policy, board = self._board(self.lines[0], melee_allowed=True)
        picked = policy._pick_alternate_dungeon(
            board,
            max_entry_depth=BLOCKED_ANGBAND_DEPTH - 1,
            prefer_deepest=True,
        )
        self.assertEqual(picked, ANTI_MELEE_CAVE)

    def _conquest_board(self, *, melee_allowed=False):
        # DECLARED CONSTRUCTED: the Mountain (the other max-depth-50 dungeon)
        # is added to the conquered set and the resistance limit reaches 50,
        # the board on which the guardianless Anti-melee cave is the deepest
        # conquest candidate.
        policy, board = self._board(self.lines[0], melee_allowed=melee_allowed)
        board = dataclasses.replace(
            board,
            conquered_dungeon_ids=tuple(board.conquered_dungeon_ids) + (14,),
        )
        return policy, board

    def test_conquest_target_never_picks_the_anti_melee_cave(self):
        policy, board = self._conquest_board()
        with mock.patch.object(policy, "_resistance_depth_limit", return_value=50):
            target = policy._conquest_target(board)
        self.assertNotEqual(target, ANTI_MELEE_CAVE)

    def test_control_conquest_target_without_the_flag(self):
        policy, board = self._conquest_board(melee_allowed=True)
        with mock.patch.object(policy, "_resistance_depth_limit", return_value=50):
            target = policy._conquest_target(board)
        self.assertEqual(target, ANTI_MELEE_CAVE)

    def _bare_low_hp(self, *, melee_allowed=False):
        # DECLARED CONSTRUCTED: the recorded board at HP 1 with an empty pack
        # (no heal, escape or recall), so the low-HP walk gate reaches its
        # adjacent-hostile answer.
        policy, board = self._board(self.lines[2], melee_allowed=melee_allowed)
        board = dataclasses.replace(
            board,
            player=dataclasses.replace(board.player, hp=1),
            inventory=[],
        )
        attacked = self._attacked_cells(board)
        walk = next(key for key in "12346789" if key not in attacked)
        policy.last_reason = "explore"
        return policy, board, walk, attacked

    def test_low_hp_walk_gate_does_not_turn_a_walk_into_melee(self):
        policy, board, walk, attacked = self._bare_low_hp()
        key = policy._low_hp_walk_gate(board, walk)
        self.assertNotEqual(policy.last_reason, "melee")
        self.assertNotIn(key, attacked)

    def test_control_low_hp_walk_gate_melees_without_the_flag(self):
        policy, board, walk, attacked = self._bare_low_hp(melee_allowed=True)
        key = policy._low_hp_walk_gate(board, walk)
        self.assertEqual(policy.last_reason, "melee")
        self.assertIn(key, attacked)

    # Specialised melee sites, each on DECLARED CONSTRUCTED recorded boards.

    def _choke(self, line, *, melee_allowed=False):
        # DECLARED CONSTRUCTED: the unseen-retreat choke point is this board's
        # cell and its hold is active (one collaborator patched).
        policy, board = self._board(line, melee_allowed=melee_allowed)
        policy._unseen_retreat_floor = board.floor_key
        policy._unseen_choke_position = board.player.position
        hostiles = [m for m in board.visible_monsters if m.hostile]
        adjacent = [m for m in hostiles if m.distance <= 1]
        with mock.patch.object(policy, "_unseen_choke_hold_active", return_value=True):
            key = policy._unseen_retreat_intercept_key(board, hostiles, adjacent)
        return key, policy.last_reason, self._attacked_cells(board)

    def test_unseen_choke_holds_instead_of_melee(self):
        for line, (turn, _key) in zip(self.lines, RECORDED):
            with self.subTest(turn=turn):
                key, reason, attacked = self._choke(line)
                # Was the adjacent attack / ``melee:choke``.
                self.assertEqual(reason, "melee:choke-hold")
                self.assertNotIn(key, attacked)

    def test_control_unseen_choke_melees_without_the_flag(self):
        key, reason, attacked = self._choke(self.lines[0], melee_allowed=True)
        self.assertEqual(reason, "melee:choke")
        self.assertIn(key, attacked)

    def _no_wait(self, line, *, melee_allowed=False, took_damage=False):
        # DECLARED CONSTRUCTED: an empty pack and no flee / least-visited
        # neighbour (two collaborators patched), so the no-wait rewrite of a
        # bare wait reaches its attack alternatives.
        policy, board = self._board(line, melee_allowed=melee_allowed)
        board = dataclasses.replace(board, inventory=[])
        policy.last_reason = "emergency:wait"
        policy._took_damage = took_damage
        with mock.patch.object(policy, "_flee_step", return_value=None), \
                mock.patch.object(policy, "_least_visited_neighbor", return_value=None):
            key = policy._forbid_wait_while_damaged(board, WAIT_KEY)
        return key, policy.last_reason, self._attacked_cells(board)

    def test_no_wait_rewrite_does_not_attack(self):
        for took_damage in (False, True):
            for line, (turn, _key) in zip(self.lines, RECORDED):
                with self.subTest(turn=turn, took_damage=took_damage):
                    key, reason, attacked = self._no_wait(line, took_damage=took_damage)
                    # Was ``no-wait:melee`` into the weakest neighbour.
                    self.assertNotIn(reason, {"no-wait:melee", "no-wait:attack"})
                    self.assertNotIn(key, attacked)

    def test_control_no_wait_rewrite_melees_without_the_flag(self):
        key, reason, attacked = self._no_wait(self.lines[0], melee_allowed=True)
        self.assertEqual(reason, "no-wait:melee")
        self.assertIn(key, attacked)

    def _breakthrough(self, line, *, melee_allowed=False):
        # DECLARED CONSTRUCTED: the adjacent monsters breed, so the breeder
        # breakthrough does not yield to the combat ladder and routes through
        # them (its ``clear-escape-path`` step is an attack).
        policy, board = self._board(line, melee_allowed=melee_allowed)
        attacked = self._attacked_cells(board)
        board = dataclasses.replace(
            board,
            visible_monsters=[
                dataclasses.replace(m, can_multiply=True) if m.distance <= 1 else m
                for m in board.visible_monsters
            ],
        )
        key = policy._breeder_breakthrough_escape_key(board)
        return key, policy.last_reason, attacked

    def test_breeder_breakthrough_does_not_step_into_a_monster(self):
        for line, (turn, _key) in zip(self.lines, RECORDED):
            with self.subTest(turn=turn):
                key, reason, attacked = self._breakthrough(line)
                # Was the step into the blocker / clear-escape-path.
                self.assertNotEqual(reason, "breeder-breakthrough:clear-escape-path")
                self.assertNotIn(key, attacked)

    def test_control_breeder_breakthrough_clears_without_the_flag(self):
        key, reason, attacked = self._breakthrough(self.lines[0], melee_allowed=True)
        self.assertEqual(reason, "breeder-breakthrough:clear-escape-path")
        self.assertIn(key, attacked)

    def test_control_shallowest_fallback_is_unchanged(self):
        # The shallow-first callers never reached 17; the flag changes nothing.
        policy, board = self._board(self.lines[0])
        control, control_board = self._board(self.lines[0], melee_allowed=True)
        self.assertEqual(
            policy._pick_alternate_dungeon(
                board, max_entry_depth=BLOCKED_ANGBAND_DEPTH - 1
            ),
            control._pick_alternate_dungeon(
                control_board, max_entry_depth=BLOCKED_ANGBAND_DEPTH - 1
            ),
        )


if __name__ == "__main__":
    unittest.main()
