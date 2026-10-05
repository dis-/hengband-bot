"""Extract only incident copies, never the live bot runtime directory."""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path('C:/hengband-backups/state-logs/mana-home-blocked-20261005-1342')
TARGET = Path(__file__).parent / 'fixtures/mana-home-20261005.json.gz'


def extract():
    payload = {'provenance': {}, 'decisions': [], 'boards': [], 'knowledge': []}
    for name in ('decisions.jsonl.gz',
                 'autorecover-20261005-134210-town-blocked-survival-mana-no-charges.bot-state-fixed.jsonl.gz',
                 'state.jsonl.gz'):
        path = SOURCE / name
        payload['provenance'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            for number, line in enumerate(stream, 1):
                raw = json.loads(line)
                if name == 'decisions.jsonl.gz':
                    kind = 'decisions' if 8930 <= number <= 8942 else None
                elif raw.get('turn', 0) < 11698758:
                    kind = None
                elif raw.get('type') == 'player_turn':
                    kind = 'boards'
                elif name.startswith('autorecover') or raw.get('type') == 'knowledge':
                    kind = 'knowledge'
                else:
                    kind = None
                if kind:
                    payload[kind].append({'source': name, 'row': number, 'raw': raw})
    TARGET.write_bytes(gzip.compress(json.dumps(payload, ensure_ascii=True).encode(), mtime=0))
    print('fixture SHA256:', hashlib.sha256(TARGET.read_bytes()).hexdigest())


if __name__ == '__main__':
    extract()
