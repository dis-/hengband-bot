"""Freeze October 5 backup rows; never access the live jsonlog."""
import gzip
import hashlib
import json
from pathlib import Path

BACKUP = Path(r'C:\hengband-backups\state-logs\owner-retired-20261005-1450')
FIXTURES = Path(__file__).parent / 'fixtures'
output = {'backup': str(BACKUP), 'sources': {}}
for kind, lines in (
    ('state-fixed', (7, 31, 32, 38, 56, 57, 66, 72, 73, 82, 88)),
    ('decisions', (205, 219, 220, 224, 227, 228, 232, 235, 236)),
):
    path = next(BACKUP.glob('*145000*.bot-' + kind + '.jsonl.gz'))
    output['sources'][kind] = {
        'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        output[kind] = [{'line': line, 'row': json.loads(text)}
                        for line, text in enumerate(stream, 1) if line in lines]
payload = json.dumps(output, ensure_ascii=False).encode('utf8')
path = FIXTURES / 'home-relief-progress-20261005.json.gz'
path.write_bytes(gzip.compress(payload, mtime=0))
print(hashlib.sha256(path.read_bytes()).hexdigest())
