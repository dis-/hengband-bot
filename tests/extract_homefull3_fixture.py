"""Freeze the read-only October 4 A/B/C incident rows and their provenance.

No policy checkpoint was retained. Consumer tests explicitly distinguish
reconstructed ledgers and command-dependent constructed responses from boards.
"""
import gzip
import hashlib
import json
from pathlib import Path

BACKUP = Path(r'C:\hengband-backups\state-logs\s33-phase2b-shadow-20261004')
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
output = {}
provenance = {}

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

for name, first, last in [('state-upto-1344.jsonl.gz', 8400160, 8400260),
                           ('state-upto-1150.jsonl.gz', 8072780, 8072808)]:
    rows, knowledge = [], {}
    onset = current_map = None
    path = BACKUP / name
    provenance[name] = digest(path)
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        for line, text in enumerate(stream, 1):
            row = json.loads(text)
            if 'grid_map' in row:
                current_map = row['grid_map']
            if row.get('type') == 'knowledge':
                knowledge[row['knowledge']['category']] = (line, row)
            if onset is None and row.get('turn', -1) >= first:
                onset = dict(knowledge)
            if (row.get('type') in {'player_turn', 'store'}
                    and 'grid_map' not in row and current_map is not None):
                row = {**row, 'grid_map': current_map}
            if first <= row.get('turn', -1) <= last:
                rows.append({'line': line, 'row': row})
    output[name] = {'states': rows, 'knowledge': onset}

for name, first, last in [
    ('autorecover-20261004-134213-equipment-transaction-home-route-repeat-terminal.bot-decisions.jsonl.gz', 273, 284),
    ('autorecover-20261004-134314-town-blocked-owner-retired.bot-decisions.jsonl.gz', 249, 281),
    ('decisions-tail-1150.jsonl.gz', 2545, 2549),
]:
    path = BACKUP / name
    provenance[name] = digest(path)
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        output[name] = [{'line': line, 'row': json.loads(text)}
                        for line, text in enumerate(stream, 1) if first <= line <= last]

payload = json.dumps(output, ensure_ascii=False).encode('utf8')
fixture = FIXTURES / 'homefull3-20261004.json.gz'
fixture.write_bytes(gzip.compress(payload, mtime=0))
provenance['fixture_sha256'] = digest(fixture)
provenance['backup_directory'] = str(BACKUP)
(FIXTURES / 'homefull3-20261004.provenance.json').write_text(
    json.dumps(provenance, indent=2), encoding='utf8')
print(provenance['fixture_sha256'])
