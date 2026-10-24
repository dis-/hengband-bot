"""S2 exit windows: recorded boards, one policy per window, ENFORCE enabled.

See town_s2_exit_replay for the declared missing-process-state walls. Expected
keys/reasons are the measured round-16 replay, not the original bot's commands:
the two-minute rolling captures remain open-loop after a command diverges.
"""
import tests  # noqa: F401

import hashlib
import gzip
import json
import unittest

from tests.town_s2_exit_replay import FIXTURES, replay_n1


class TownTerminalExitWindowsTest(unittest.TestCase):
    def test_recorded_decisions_align_with_fixture_boards(self):
        metadata = json.loads((FIXTURES / 'town-s2-n1-windows.json').read_text(encoding='utf8'))
        for name, window in metadata.items():
            with self.subTest(capture=name):
                fixture = FIXTURES / window['fixture']
                self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), window['sha256'])
                with gzip.open(fixture, 'rt', encoding='utf8') as stream:
                    rows = [json.loads(line) for line in stream]
                self.assertEqual(
                    [rows[index]['turn'] for index in window['decide_at']],
                    [decision['turn'] for decision in window['decisions']])
                self.assertEqual({rows[index]['type'] for index in window['decide_at']},
                                 {'player_turn'})

    def check_window(self, name):
        metadata = json.loads((FIXTURES / 'town-s2-n1-windows.json').read_text(encoding='utf8'))[name]
        self.assertEqual(hashlib.sha256((FIXTURES / metadata['fixture']).read_bytes()).hexdigest(),
                         metadata['sha256'])
        expected = json.loads((FIXTURES / 'town-s2-exit-expected.json').read_text(encoding='utf8'))[name]
        trace = replay_n1(name)
        self.assertEqual([row['turn'] for row in trace],
                         [row['turn'] for row in metadata['decisions']])
        self.assertEqual([[row['turn'], row['key'], row['reason']] for row in trace], expected['trace'])
        self.assertEqual(sum(len(row['admissions']) for row in trace), expected['refused'])
        for step in trace:
            for row in step['admissions']:
                self.assertEqual(row['verdict'], 'refused')
                self.assertEqual(row['mode'], 'enforce')
                self.assertTrue(row['closed'] or row['live'], row)

    def test_63_first_capture(self):
        self.check_window('20261018-071312')

    def test_63_second_capture(self):
        self.check_window('20261018-074006')

    def test_64_capture(self):
        self.check_window('20261018-091516')

    def test_66_second_capture(self):
        self.check_window('20261018-140156')

    def test_66_third_capture(self):
        self.check_window('20261019-0050')

    def test_68_first_capture(self):
        self.check_window('20261018-144235')

    def test_68_second_capture(self):
        self.check_window('20261018-144457')

    def test_94_first_capture(self):
        self.check_window('20261020-135723')

    def test_94_second_capture(self):
        self.check_window('20261020-140000')

    def test_76_capture(self):
        self.check_window('20261019-080433')

    def test_n1a_first_window(self):
        self.check_window('20261023-183351')

    def test_n1a_second_window(self):
        self.check_window('20261023-183418')

    def test_n1a_third_window(self):
        self.check_window('20261023-183436')


if __name__ == '__main__':
    unittest.main()
