"""The key-wise merge driver for the town work JSON objects (whole-bot review 2026-11-23 (a)-11).

Two branches that touch neighbouring keys of town_work_sites.json conflicted line by line;
scripts/json_key_merge.py merges them key by key and keeps git's conflict when both sides
changed one key.
"""
import tests  # noqa: F401 -- isolate runtime files
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import json_key_merge as driver  # noqa: E402


def row(classification):
    return dict(classification=classification, rows=['survival'], delegation='selected child')


class JsonKeyMergeTest(unittest.TestCase):
    def run_driver(self, base, ours, theirs):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp, name) for name in ('base', 'ours', 'theirs')]
            for path, obj in zip(paths, (base, ours, theirs)):
                path.write_text(driver.dump(obj), encoding='utf-8', newline='\n')
            code = subprocess.run([sys.executable, str(ROOT / 'scripts/json_key_merge.py'), *map(str, paths)],
                                  capture_output=True).returncode
            return code, paths[1].read_bytes()

    def test_neighbouring_additions_merge_sorted_in_generator_bytes(self):
        base = {'a.py:f': row('data'), 'c.py:h': row('data')}
        ours = {**base, 'b.py:g': row('producer')}
        theirs = {**base, 'b.py:gg': row('adapter')}
        code, merged = self.run_driver(base, dict(sorted(ours.items())), dict(sorted(theirs.items())))
        self.assertEqual(code, 0)
        expected = dict(sorted({**ours, **theirs}.items()))
        self.assertEqual(merged, driver.dump(expected).encode('utf-8'))

    def test_one_side_change_and_removal_win(self):
        base = {'a.py:f': row('data'), 'b.py:g': row('data'), 'c.py:h': row('data')}
        ours = {'a.py:f': row('producer'), 'b.py:g': row('data'), 'c.py:h': row('data')}
        theirs = {'a.py:f': row('data'), 'c.py:h': row('data')}
        self.assertEqual(driver.merge(base, ours, theirs), ({'a.py:f': row('producer'), 'c.py:h': row('data')}, None))

    def test_unsorted_reviews_keep_ours_order_then_theirs_new_keys(self):
        base = {'z.py:a': row('data')}
        merged, _ = driver.merge(base, {**base, 'm.py:b': row('data')}, {**base, 'b.py:c': row('data')})
        self.assertEqual(list(merged), ['z.py:a', 'm.py:b', 'b.py:c'])

    def test_clean_line_merge_keeps_its_bytes(self):
        base = {'z.py:a': row('data'), 'y.py:b': row('data'), 'x.py:c': row('data'), 'w.py:d': row('data')}
        ours = {'m.py:new': row('data'), **base}
        theirs = {**base, 'b.py:new': row('data')}
        code, merged = self.run_driver(base, ours, theirs)
        self.assertEqual(code, 0)
        self.assertEqual(list(json.loads(merged)), ['m.py:new', 'z.py:a', 'y.py:b', 'x.py:c', 'w.py:d', 'b.py:new'])

    def test_both_changed_one_key_falls_back_to_line_conflict(self):
        base = {'a.py:f': row('data')}
        code, merged = self.run_driver(base, {'a.py:f': row('producer')}, {'a.py:f': row('adapter')})
        self.assertEqual(code, 1)
        self.assertIn(b'<<<<<<< ours', merged)

    def test_foreign_format_is_not_redumped(self):
        self.assertIsNone(driver.load(json.dumps({'a': 1}).encode('utf-8')))
        self.assertEqual(driver.load(driver.dump({'a': 1}).encode('utf-8')), {'a': 1})

    def test_attributes_route_both_town_work_objects_to_the_driver(self):
        for path in ('src/hengbot/town_work_sites.json', 'scripts/town_work_review.json'):
            out = subprocess.run(['git', 'check-attr', 'merge', '--', path], cwd=ROOT,
                                 capture_output=True, text=True).stdout
            self.assertTrue(out.strip().endswith('merge: json-keys'), out)


if __name__ == '__main__':
    unittest.main()
