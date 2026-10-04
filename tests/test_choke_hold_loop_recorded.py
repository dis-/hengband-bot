"""Parked-episode regression from the read-only 2026-10-05 backup.

Onset states no longer exist in the backup. The recorded boards and decisions
are exact; injection of an already-active retreat at the parked choke is
declared, not claimed to be a lifetime replay. No combat/hold producer is
mocked in the recorded release pin. Constructed clock tests separately keep
damage above the lower bound to exercise expiry independently.
Bookkeeping wall: suppress the ~f skill-list request (its response was rotated
out); it precedes all dungeon decisions and does not affect damage or movement.
"""
import tests  # noqa: F401
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hengbot.model import Position, Snapshot, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, WAIT_KEY
from policy_fixtures import grid, hostile, player

FIXTURE = Path(__file__).parent / 'fixtures/choke-hold-loop-20261005.jsonl.gz'
HOLDS = {'unseen:choke-wait', 'melee:choke-hold'}


def arm(policy, snapshot, start):
    policy._unseen_retreat_floor = snapshot.floor_key
    policy._unseen_choke_position = snapshot.player.position
    policy._unseen_retreat_target = snapshot.player.position
    policy._unseen_retreat_direction = (-1, 0)
    policy._unseen_choke_started_turn = start
    # Baseline fields: let the same pin run against the pre-fix implementation.
    policy._unseen_wait_remaining = 59
    policy._unseen_wait_intercepted = False
    policy._escape_state.enter('unseen', 'unseen:reverse-choke')


class ChokeHoldLoopRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
            'e94fb77966efd89c9c1c5ca09d86febd1241d5d428274f48fac6ce8d3a310318')
        with gzip.open(FIXTURE, 'rt', encoding='utf-8') as stream:
            cls.records = [json.loads(line) for line in stream]
        cls.knowledge = load_monrace_knowledge(
            Path('C:/hengband/lib/edit/MonraceDefinitions.jsonc'))

    def test_recorded_parked_hold_releases_in_public_decision(self):
        onset = self.records[0]['decision']
        self.assertEqual(onset['turn'], 10457786)
        for record in self.records[1:]:
            with self.subTest(line=record['line_number']):
                decision = record['decision']
                self.assertIn(decision['reason'], HOLDS)
                self.assertEqual(decision['threat_prediction']['total'], 0)
                self.assertGreater(decision['turn'] - onset['turn'], 500)
                snapshot = parse_snapshot(record['board'], self.knowledge)
                policy = HengbotPolicy(monrace_knowledge=self.knowledge)
                policy.prime(snapshot)
                arm(policy, snapshot, onset['turn'])
                with patch.object(policy, '_skill_exp_request_key', return_value=None):
                    key = policy.choose_key(snapshot)
                self.assertNotIn(policy.last_reason, HOLDS, (key, policy.last_reason))
                self.assertEqual((key, policy.last_reason), ('8', 'explore'))
                self.assertIsNone(policy._unseen_retreat_floor)
                self.assertNotEqual(policy._escape_state.owner, 'unseen')

    def _clock_board(self):
        return Snapshot(player(10, 10, hp=200, max_hp=200),
                        {Position(10, x): grid(10, x) for x in range(9, 13)},
                        [], turn=1000, floor_key=(3, 23, 0))

    def test_alternating_producers_share_500_game_turn_deadline(self):
        snapshot = self._clock_board()
        policy = HengbotPolicy()
        policy.prime(snapshot)
        arm(policy, snapshot, snapshot.turn)
        remembered = hostile(32, 10, 12, distance=2)
        # CONSTRUCTED damage only: keep >=10%, with no sighting on the board.
        with patch.object(policy, '_choke_predicted_damage', return_value=20):
            for elapsed in range(0, 500, 5):
                board = replace(snapshot, turn=1000 + elapsed)
                if elapsed % 10 == 0:
                    key = policy._unseen_retreat_intercept_key(board, [remembered], [])
                    expected = 'melee:choke-hold'
                else:
                    key = policy._unseen_retreat_key(board, [])
                    expected = 'unseen:choke-wait'
                self.assertEqual((key, policy.last_reason), (WAIT_KEY, expected))
            board = replace(snapshot, turn=1500)
            self.assertIsNone(policy._unseen_retreat_intercept_key(board, [remembered], []))
            self.assertIsNone(policy._unseen_retreat_key(board, []))
        self.assertIsNone(policy._unseen_retreat_floor)

    def test_low_damage_releases_both_producers_before_deadline(self):
        for intercept in (False, True):
            for damage in (0, 19):
                with self.subTest(intercept=intercept, damage=damage):
                    board = self._clock_board()
                    policy = HengbotPolicy()
                    policy.prime(board)
                    arm(policy, board, board.turn)
                    with patch.object(policy, '_choke_predicted_damage', return_value=damage):
                        key = (policy._unseen_retreat_intercept_key(board, [hostile(32, 10, 12)], [])
                               if intercept else policy._unseen_retreat_key(board, []))
                    self.assertIsNone(key)
                    self.assertIsNone(policy._unseen_retreat_floor)

    def test_clock_counts_game_turns_not_decisions_and_survives_sighting(self):
        board = self._clock_board()
        policy = HengbotPolicy()
        policy.prime(board)
        arm(policy, board, 1000)
        enemy = hostile(32, 10, 11, max_melee_damage=20)
        with patch.object(policy, '_choke_predicted_damage', return_value=20):
            for _ in range(100):
                self.assertEqual(policy._unseen_retreat_key(board, []), WAIT_KEY)
            seen = replace(board, turn=1499, visible_monsters=[enemy])
            self.assertEqual(policy._unseen_retreat_intercept_key(seen, [enemy], [enemy]), '6')
            self.assertEqual(policy._unseen_choke_started_turn, 1000)
            self.assertIsNone(policy._unseen_retreat_key(replace(board, turn=1500), []))

    def test_clear_removes_clock_and_next_episode_gets_new_start(self):
        board = self._clock_board()
        policy = HengbotPolicy()
        policy.prime(board)
        arm(policy, board, 1000)
        policy._clear_unseen_retreat()
        self.assertIsNone(policy._unseen_choke_started_turn)
        policy._unseen_retreat_floor = board.floor_key
        policy._unseen_retreat_target = board.player.position
        with patch.object(policy, '_choke_predicted_damage', return_value=20):
            self.assertEqual(policy._unseen_retreat_key(replace(board, turn=2000), []), WAIT_KEY)
        self.assertEqual(policy._unseen_choke_started_turn, 2000)

    def test_arrival_with_zero_damage_retires_without_first_wait(self):
        board = self._clock_board()
        policy = HengbotPolicy()
        policy.prime(board)
        policy._unseen_retreat_floor = board.floor_key
        policy._unseen_retreat_target = board.player.position
        policy._escape_state.enter('unseen', 'unseen:reverse-choke')
        # Legacy fields solely for the independently reverted producer probe.
        policy._unseen_wait_remaining = 0
        policy._unseen_wait_intercepted = False
        self.assertIsNone(policy._unseen_retreat_key(board, []))
        self.assertIsNone(policy._unseen_retreat_floor)
        self.assertIsNone(policy._unseen_choke_started_turn)


if __name__ == '__main__':
    unittest.main()
