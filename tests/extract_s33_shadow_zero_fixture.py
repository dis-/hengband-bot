"""Freeze the 80 incident rows and exact available boards from backup copies."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(r'C:\hengband-backups\state-logs\s33-phase2b-shadow-20261004')
TARGET = Path(__file__).parent / 'fixtures/s33-shadow-zero-20261005.json.gz'


def extract():
    source = ROOT / 'shadow-rows-since-1000.jsonl.gz'
    rows = [json.loads(line) for line in gzip.open(source, 'rt', encoding='utf8')]
    assert len(rows) == 80
    data = {'rows': rows, 'sources': {}, 'boards': {}, 'prior': {}, 'knowledge': {}}
    data['sources'][source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    wanted = {row['turn'] for row in rows}
    # Only backup copies; never access a live log or checkpoint.
    names = ['state-at-1225.jsonl.gz', 'state-upto-1150.jsonl.gz',
             'autorecover-20261004-121956-exit-no-marker.bot-state-fixed.jsonl.gz',
             'autorecover-20261004-122359-exit-no-marker.bot-state-fixed.jsonl.gz']
    for name in names:
        path = ROOT / name
        data['sources'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        grid = None
        knowledge = {}
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            for line_number, line in enumerate(stream, 1):
                raw = json.loads(line)
                grid = raw.get('grid_map', grid)
                if raw.get('type') == 'knowledge':
                    category = (raw.get('knowledge') or {}).get('category')
                    if category in {'skill_exp', 'home'}:
                        knowledge[category] = {'source': f'{name}:{line_number}', 'raw': raw}
                if raw.get('turn') not in wanted or raw.get('type') not in {'player_turn', 'store'}:
                    continue
                for n, row in enumerate(rows, 1):
                    if (row['turn'] == raw['turn'] and row['position'] == {
                            'y': raw['player']['y'], 'x': raw['player']['x']}
                            and row.get('store_type') == (raw.get('store') or {}).get('store_type')):
                        # Keep the first exact board; materialize only its inherited map.
                        data['boards'].setdefault(str(n), {'source': f'{name}:{line_number}',
                            'raw': {**raw, **({'grid_map': grid} if 'grid_map' not in raw and grid else {})}})
                        data['knowledge'].setdefault(str(n), dict(knowledge))
    decisions = ['decisions-at-1225.jsonl.gz', 'decisions-1-at-1225.jsonl.gz']
    decisions += [p.name for p in ROOT.glob('autorecover-*.bot-decisions.jsonl.gz')]
    for name in decisions:
        latest = {}
        used = False
        with gzip.open(ROOT / name, 'rt', encoding='utf8') as stream:
            for line_number, line in enumerate(stream, 1):
                row = json.loads(line)
                for n, incident in enumerate(rows, 1):
                    if (row.get('time'), row.get('decision_sequence')) == (incident['time'], incident['decision_sequence']):
                        holder_id = incident['claim']['s33_shadow']['holder_claim_id']
                        if holder_id in latest:
                            data['prior'].setdefault(str(n), {'source': f'{name}:{latest[holder_id][0]}',
                                                           'row': latest[holder_id][1]})
                            used = True
                claim = row.get('claim') or {}
                if claim.get('claim_id') is not None:
                    latest[claim['claim_id']] = (line_number, row)
        if used:
            data['sources'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    TARGET.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode('utf8'), mtime=0))
    print('fixture sha256', hashlib.sha256(TARGET.read_bytes()).hexdigest())
    print('rows', len(rows), 'boards', len(data['boards']), 'prior holders', len(data['prior']))
    print('board rows', ','.join(data['boards']))


if __name__ == '__main__':
    extract()
