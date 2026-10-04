"""Extract immutable incident seams from copies only (no live runtime access)."""
import copy
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(r'C:\hengband-backups\state-logs\s33-phase2b-shadow-20261004')
TARGET = Path(__file__).parent / 'fixtures/shadow3-20261004.json.gz'


def extract():
    data = {'sources': {}, 'rows': {}, 'boards': {}, 'knowledge': {}}
    selections = {'decisions-1-at-1740.jsonl.gz': range(574, 580),
                  'decisions-1714-1740.jsonl.gz': (*range(2438, 2447), *range(3768, 3785))}
    turns = set()
    for name, numbers in selections.items():
        data['sources'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        with gzip.open(ROOT/name, 'rt', encoding='utf8') as stream:
            for n, line in enumerate(stream, 1):
                if n in numbers:
                    row = json.loads(line)
                    data['rows'][f'{name}:{n}'] = row
                    turns.add(row.get('turn'))
    for name in ('state-upto-1637.jsonl.gz', 'state-upto-1740.jsonl.gz',
                 'autorecover-20261004-173350-no-key-exhausted.bot-state-fixed.jsonl.gz'):
        data['sources'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        grid_map = None
        with gzip.open(ROOT/name, 'rt', encoding='utf8') as stream:
            for n, line in enumerate(stream, 1):
                raw = json.loads(line)
                grid_map = raw.get('grid_map', grid_map)
                turn = raw.get('turn')
                if turn not in turns:
                    continue
                if raw.get('type') == 'knowledge':
                    data['knowledge'][f'{turn}:{name}:{n}'] = raw
                if raw.get('type') not in {'store', 'player_turn'}:
                    continue
                board = copy.deepcopy(raw)
                if grid_map is not None and 'grid_map' not in board:
                    board['grid_map'] = copy.deepcopy(grid_map)
                key = f"{turn}:{raw['type']}:{name}:{n}"
                data['boards'][key] = board
    TARGET.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode('utf8'), mtime=0))
    print('fixture', hashlib.sha256(TARGET.read_bytes()).hexdigest())
    print('boards', list(data['boards']))
    print('knowledge', list(data['knowledge']))


if __name__ == '__main__':
    extract()
