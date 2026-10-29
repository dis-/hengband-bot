"""Check saved evidence, unchanged existing tests, and clean production trees."""
import json
from pathlib import Path
import subprocess

out = Path(__file__).resolve().parent
root = out.parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, encoding='utf-8').strip()


assert not git('status', '--porcelain', '--', 'src', 'tests')
changed_tests = git('diff', '--name-only', 'main', '--', 'tests').splitlines()
assert changed_tests == ['tests/test_census_owner_declaration.py'], changed_tests
incident = json.loads((out / 'incident-tests.json').read_text(encoding='utf-8'))
incident_files = sorted({'/'.join(name.split('.')[:2]) + '.py' for name in incident})
assert not git('diff', '--name-only', '78deea2ac', 'eebc99f0e', '--', *incident_files)
assert not git('diff', '--name-only', 'main', '--', 'scripts/ownership_claim_exceptions.txt',
               'scripts/item_sink_adapters.json')
checks = {name: json.loads((out / (name + '-result.json')).read_text(encoding='utf-8'))
          for name in ('focused-head', 'related-head', 'preflight-clean', 'fast-tier-head', 'mutation')}
assert checks['focused-head']['code'] == 1
for name in ('related-head', 'preflight-clean', 'fast-tier-head', 'mutation'):
    assert checks[name]['code'] == 0, name
source_head = checks['mutation']['head']
trees = [git('rev-parse', 'HEAD:' + path) for path in ('src/hengbot', 'tests')]
assert trees == [git('rev-parse', source_head + ':' + path) for path in ('src/hengbot', 'tests')]
record_path = Path('C:/hengband-backups/mutation-records') / (source_head + '.txt')
record = record_path.read_text(encoding='utf-8')
assert 'MUTATION OK' in record
report = (root / 'LUNA-REPORT-main-red-261029-0610.txt').read_text(encoding='utf-8')
assert '未完了（報告確定前' not in report
assert not report.startswith('\ufeff')
assert all(ord(char) >= 32 or char in '\n\t' for char in report)
payload = dict(source_head=source_head, current_head=git('rev-parse', 'HEAD'),
               source_test_trees=trees, changed_tests=changed_tests,
               source_and_tests_clean=True, mutation_record=record,
               checks={name: row['code'] for name, row in checks.items()},
               report_utf8=True)
(out / 'final-audit.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print('Evidence audit OK')
