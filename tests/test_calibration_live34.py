"""Recorded calibration entry windows; never consume a response after a changed key.

Entry wall: a fresh policy attaches at the first recorded calibration deposit,
with the last observed Home/skill catalogue and a production calibration begin.
No historical commands are injected. Each selected board is ordered protocol
input; intermediate store pages of a posted macro are not extra decisions.
"""
import tests  # noqa: F401
import gzip
import json
import pickle
import unittest
from pathlib import Path
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.recorded_loadout import recorded_loadout_replay

LABELS = ('0317', '0812', '0812b', '1041', '1235', '1342', '1416')
FIXTURES = Path(__file__).parent / 'fixtures'


def payload(label):
    with gzip.open(FIXTURES / f'live34-{label}.json.gz', 'rt', encoding='utf8') as source:
        return json.load(source)


def knowledge(policy, row):
    if row.get('type') == 'character':
        policy.observe_character_snapshot(row['character'])
    category = row.get('knowledge', {}).get('category')
    if category == 'home':
        policy.consume_home_knowledge(tuple(_parse_items(row['knowledge']['items'])))
    elif category == 'skill_exp':
        policy.consume_skill_knowledge(row)


@recorded_loadout_replay
def replay(label, on, checkpoint=False, phase="deposit"):
    data = payload(label)
    raw = data['state']
    decisions = data['decisions']
    if phase == 'strip':
        first = next(r for r in decisions if r['reason'] == 'equipment-transaction:takeoff')
        decisions = [r for r in decisions if r['decision_sequence'] >= first['decision_sequence']]
        raw = [r for r in raw if r.get('turn', 0) >= first['turn']]
    policy = HengbotPolicy()
    policy._town_claim_bar_enforced = on
    policy._crossarea_fundraising_enforced = True
    initial = parse_snapshot(next(r for r in raw if r['type'] == 'player_turn'), {})
    policy.observe_town_visit_epoch(True, data['start'])
    for row in data['knowledge']:
        knowledge(policy, row)
    policy._observe(initial)
    policy._begin_character_calibration(initial)
    if phase == "strip":
        if not policy._install_calibration_strip_session(initial):
            raise AssertionError("recorded strip cannot be installed")
    cursor = 0
    measured = []
    for live in decisions:
        # Atomic entry's tail runs on the first store page; other calibration
        # steps run on player_turn boards. Knowledge responses are consumed
        # before the next decision, in their actual protocol order.
        tail = live['reason'].startswith('home:') and (live.get('key') or '').startswith('d')
        candidates = [i for i in range(cursor, len(raw))
                      if raw[i].get('turn') == live['turn']
                      and raw[i]['type'] == ('store' if tail else 'player_turn')]
        if not candidates:
            return measured, {'sequence': live['decision_sequence'], 'boundary': 'no-decision-board'}
        index = candidates[0]
        for row in raw[cursor:index]:
            knowledge(policy, row)
        board = parse_snapshot(raw[index], {})
        if checkpoint:
            policy._town_need_specs = None
            policy = pickle.loads(pickle.dumps(policy))
        key = policy.choose_key(board)
        shadow = policy._s33_shadow_verdict(board, key)
        entry = {'sequence': live['decision_sequence'], 'turn': live['turn'],
                 'key': key, 'reason': policy.last_reason, 'shadow': shadow['would_stop'],
                 'execution': (policy.decision_claim or {}).get('execution')}
        measured.append(entry)
        if key != live['key']:
            return measured, {'sequence': live['decision_sequence'], 'boundary': 'changed-key',
                              'live_key': live['key'], 'live_reason': live['reason']}
        if key is not None:
            policy.confirm_key_posted(key)
        cursor = index + 1
    return measured, {'boundary': 'capture-end', 'debt': len(policy._calibration_restore_signatures)}


class CalibrationLive34Test(unittest.TestCase):
    def test_all_recorded_sequences_have_no_on_stop_and_shadow_agrees(self):
        for label in LABELS:
            with self.subTest(label=label):
                off, off_end = replay(label, False)
                on, on_end = replay(label, True)
                print(label, 'entry', len(off), off_end, len(on), on_end)
                self.assertTrue(on)
                self.assertFalse(any(row['reason'].startswith('ownership:') for row in on), on)
                self.assertFalse(any(row['shadow'] is not None for row in off), off)
                for row in on:
                    self.assertIsNone(row['shadow'])
                    if row['key'] is not None:
                        self.assertIsNotNone(row['execution'])
                restored, end = replay(label, True, checkpoint=True)
                self.assertEqual([(r['key'], r['reason'], r['shadow']) for r in restored],
                                 [(r['key'], r['reason'], r['shadow']) for r in on])
                self.assertEqual(end, on_end)

    def test_recorded_strip_executor_keeps_its_calibration_owner(self):
        for label in LABELS:
            if label == '1342':
                continue  # Capture ends before the strip begins.
            with self.subTest(label=label):
                off, off_end = replay(label, False, phase='strip')
                on, on_end = replay(label, True, phase='strip')
                print(label, 'strip', json.dumps({'off': off, 'on': on,
                      'off_end': off_end, 'on_end': on_end}))
                self.assertFalse(any(r['reason'].startswith('ownership:') for r in on), on)
                self.assertFalse(any(r['shadow'] is not None for r in off), off)
                self.assertEqual([(r['key'], r['reason']) for r in off],
                                 [(r['key'], r['reason']) for r in on])
                restored, end = replay(label, True, checkpoint=True, phase='strip')
                self.assertEqual([(r['key'], r['reason'], r['shadow']) for r in restored],
                                 [(r['key'], r['reason'], r['shadow']) for r in on])
                self.assertEqual(end, on_end)


if __name__ == '__main__':
    unittest.main()
