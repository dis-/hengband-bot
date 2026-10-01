"""Recorded calibration entry windows; never consume a response after a changed key.

Entry wall: a fresh policy attaches at the first recorded calibration deposit,
with the last observed Home/skill catalogue and a production calibration begin.
No historical commands are injected. Each selected board is ordered protocol
input; intermediate store pages of a posted macro are not extra decisions.
"""
import tests  # noqa: F401
import gzip
import hashlib
import json
import pickle
import unittest
from pathlib import Path
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.recorded_loadout import recorded_loadout_replay

LABELS = ('0317', '0812', '0812b', '1041', '1235', '1342', '1416')
FIXTURES = Path(__file__).parent / 'fixtures'
FIXTURE_SHA = {'0317': '2295758e04fc810ac5e43245c745ad7e6c32b746cfced7525d38f1a8c1b9a2f7', '0812': 'c348eb3c9052b34a1190931ac9f81237066f6bf3afe7157209370641a4a94e0c', '0812b': 'ad8067c9cf1cb188a061c24c6978e3dbf8b98c29bd815f837ab65a02867a6fc2', '1041': 'f7d2777f4f05832fe67c14793feab0d11905c191c708e1e5c118ec9cba886b46', '1235': '898fb0b38e9578c036fd2210922de8236bc94c138b3ac939f3d9f48fe1078bff', '1342': '478285550c0e54ca616155a69c1dcfb488fd32650e3f59cede95d02348b7d707', '1416': 'bce411437f7b703b49d1e5c1d897989be25530ef22079c5adfdcb28171927d5e'}


def payload(label):
    with gzip.open(FIXTURES / f'live34-{label}.json.gz', 'rb') as source:
        body = source.read()
    if hashlib.sha256(body).hexdigest() != FIXTURE_SHA[label]:
        raise AssertionError(f'changed recorded substrate: {label}')
    return json.loads(body)


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
    if phase in {'strip', 'restore'}:
        first = next(r for r in decisions if r['reason'] == ('equipment-transaction:takeoff' if phase == 'strip'
                         else 'calibration:request-restore-knowledge'))
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
    if phase == 'restore':
        # Independent restore attachment: register the exact historically
        # deposited quantities through the real deposit producer. These are
        # confirmed facts at the restore boundary, not forced decisions.
        import re
        original = data['state']
        for deposit in data['decisions']:
            macro = deposit.get('key') or ''
            if not macro.startswith('d'):
                continue
            before = parse_snapshot(next(r for r in original
                if r['turn'] == deposit['turn'] and r['type'] == 'player_turn'), {})
            commands = []
            for slot, quantity in re.findall(r'd([a-z])(\d*\r)?', macro):
                item = next(i for i in before.inventory if i.slot == slot)
                commands.append(policy._home_deposit_key(before, item,
                    forced_count=int(quantity) if quantity else 1))
            if ''.join(commands) != macro.removesuffix('\x1b'):
                raise AssertionError(f'changed historical deposit intent: {label}')
        # The confirmed deposits changed Home's page-relative addresses.
        # Apply the same production invalidation before the recorded ~9.
        policy._invalidate_home_observation()
        policy._calibration_phase = 'restore-supplies'
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
            raise AssertionError(f"missing recorded decision board: {label}/{live['decision_sequence']}")
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
            holder = policy._claim_errand_hold('__none__', enforced=True)
            if holder is not None and holder.owner.value == 'calibration':
                entry['posted_stop'] = policy._town_holder_structural_stop(holder, board)
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
                self.assertFalse(any(r.get('posted_stop') is not None for r in on), on)
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

    def test_recorded_restore_entry_declares_knowledge_and_home_work(self):
        for label in LABELS[:-2]:
            with self.subTest(label=label):
                off, off_end = replay(label, False, phase='restore')
                on, on_end = replay(label, True, phase='restore')
                print(label, 'restore', json.dumps({'off': off, 'on': on,
                      'off_end': off_end, 'on_end': on_end}))
                self.assertTrue(on)
                self.assertFalse(any(r.get('posted_stop') is not None for r in on), on)
                self.assertFalse(any(r['reason'].startswith('ownership:') for r in on), on)
                self.assertFalse(any(r['shadow'] is not None for r in off), off)
                self.assertEqual([(r['key'], r['reason']) for r in off],
                                 [(r['key'], r['reason']) for r in on])
                restored, end = replay(label, True, checkpoint=True, phase='restore')
                self.assertEqual([(r['key'], r['reason'], r['shadow']) for r in restored],
                                 [(r['key'], r['reason'], r['shadow']) for r in on])
                self.assertEqual(end, on_end)


if __name__ == '__main__':
    unittest.main()
