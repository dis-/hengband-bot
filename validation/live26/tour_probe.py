"""Read-only revision comparison using the authorized tour module's replay.

Usage: python validation/live26/tour_probe.py REV OUTPUT [--prefix]
Only src/ is extracted under this worktree; the checked-in replay and pins
remain unchanged. --prefix stops before list index 2661, after the incident.
"""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]


def summarize(rows):
    next_rows = []
    index = 0
    while index < len(rows):
        end = index
        while end + 1 < len(rows) and rows[end + 1]['claim_id'] == rows[index]['claim_id']:
            end += 1
        closed = (rows[end + 1].get('closed_claim') or {}) if end + 1 < len(rows) else {}
        if (rows[index]['goal']['kind'] == 'Reach' and end == index
                and closed.get('claim_id') == rows[index]['claim_id']
                and closed.get('closed') == 'complete'):
            next_rows.append([rows[index]['decision_sequence'], rows[index]['reason']])
        index = end + 1
    return {
        'rows': len(rows), 'next_row_complete': len(next_rows),
        'next_rows': next_rows,
        'incident': [row for row in rows if 2640 <= row['decision_sequence'] <= 2660],
        'violations': [[row['decision_sequence'], v['kind'], v['from'], v['to']]
                       for row in rows if isinstance(v := row.get('violation'), dict)
                       and v.get('scope') == 'S3'],
    }


def main():
    revision, output = sys.argv[1:3]
    with TemporaryDirectory(prefix='source-', dir=ROOT / 'validation/live26') as raw:
        if revision != 'current':
            archive = subprocess.check_output(['git', 'archive', revision, 'src'], cwd=ROOT)
            with tarfile.open(fileobj=io.BytesIO(archive)) as source:
                source.extractall(raw, filter='data')
            sys.path.insert(0, str(Path(raw) / 'src'))
        sys.path.insert(1, str(ROOT))
        from tests.test_unaffordable_claim_tour_recorded import UnaffordableClaimTourRecordedTest as T
        from hengbot.policy import HengbotPolicy
        original = HengbotPolicy.choose_key

        class PrefixEnd(Exception):
            pass

        def choose(policy, snapshot):
            if '--prefix' in sys.argv and T.claim_rows is not None and len(T.claim_rows) >= 2661:
                raise PrefixEnd()
            if T.claim_rows is not None and len(T.claim_rows) % 500 == 0:
                print('row', len(T.claim_rows), flush=True)
            return original(policy, snapshot)

        HengbotPolicy.choose_key = choose
        T.setUpClass()
        try:
            T._replay()
        except PrefixEnd:
            pass
        finally:
            HengbotPolicy.choose_key = original
        result = {'revision': revision, **summarize(T.claim_rows)}
        Path(output).write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2), encoding='utf8')
        print(json.dumps({k: result[k] for k in ('revision', 'rows', 'next_row_complete', 'violations')}), flush=True)


if __name__ == '__main__':
    main()
