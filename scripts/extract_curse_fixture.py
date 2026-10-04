import gzip
import hashlib
import json
from pathlib import Path

source = Path(r'C:\hengband-backups\state-logs\s33-phase2b-shadow-20261004')
pins = {}

def pin(label, name, row, data):
    pins[label] = {'source': name, 'row': row, 'data': data}

for name in ('state-upto-1834.jsonl.gz',
             'autorecover-20261004-191650-town-blocked-departure-unsatisfiable.bot-state-fixed.jsonl.gz',
             'autorecover-20261004-192945-no-key-exhausted.bot-state-fixed.jsonl.gz',
             'autorecover-20261004-193603-stuck-prompt-stuck-recall-escape.bot-state-fixed.jsonl.gz'):
    last = None
    with gzip.open(source / name, 'rt', encoding='utf-8') as stream:
        for row, line in enumerate(stream, 1):
            data = json.loads(line)
            if 'equipment' not in data:
                continue
            last = row, data
            if data.get('turn') in (9002633, 9018634):
                pin(str(data['turn']), name, row, data)
            if data.get('floor', {}).get('in_town') and 'town' not in pins:
                pin('town', name, row, data)
            if data.get('knowledge', {}).get('category') == 'home':
                items = data['knowledge'].get('items', [])
                if 'home' not in pins and any(it.get('tval') == 70 and it.get('sval') in (14, 15) for it in items):
                    pin('home', name, row, data)
            if (data.get('floor', {}).get('dungeon_id') == 2
                    and data['floor'].get('level') == 1 and 'mine' not in pins):
                pin('mine', name, row, data)
    if '191650' in name:
        pin('blocked', name, *last)
    if '193603' in name:
        pin('recall', name, *last)
for name in ('decisions-1-at-1955.jsonl.gz',
             'autorecover-20261004-191650-town-blocked-departure-unsatisfiable.bot-decisions.jsonl.gz'):
    with gzip.open(source / name, 'rt', encoding='utf-8') as stream:
        for row, line in enumerate(stream, 1):
            data = json.loads(line)
            if data.get('reason') in ('fundraise:wield-digging-tool', 'fundraise:abandon-unwieldable-digger',
                                     'town:blocked:departure-unsatisfiable', 'stuck:recall-escape'):
                label = data['reason']
                if label not in pins:
                    pin(label, name, row, data)
name = 'autorecover-20261004-193603-stuck-prompt-stuck-recall-escape.bot-stderr.log'
for row, line in enumerate((source / name).read_text(encoding='utf-8').splitlines(), 1):
    if 'unowned confirm:' in line:
        pin('recall-prompt', name, row, {'text': line.split('unowned confirm: ', 1)[1]})
fixture = Path('tests/fixtures/curse-priority-20261004.json.gz')
fixture.parent.mkdir(exist_ok=True)
with fixture.open('wb') as raw:
    with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as stream:
        stream.write(json.dumps(pins, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
print('SHA256', hashlib.sha256(fixture.read_bytes()).hexdigest())
print([(label, value['source'], value['row'], value['data'].get('turn')) for label, value in pins.items()])
