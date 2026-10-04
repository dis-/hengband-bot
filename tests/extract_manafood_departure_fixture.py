"""Copy incident boards verbatim; never read the live runtime directory."""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path('C:/hengband-backups/state-logs/s33-phase2b-shadow-20261004')
TARGET = Path(__file__).parent / 'fixtures/manafood-20261004.json.gz'


def extract():
    payload = {'boards': {}, 'decisions': [], 'provenance': {}}
    source = SOURCE / 'state-upto-1637.jsonl.gz'
    with gzip.open(source, 'rt', encoding='utf8') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if row.get('turn') == 8795606 and row.get('knowledge', {}).get('category') == 'skill_exp':
                payload.setdefault('recovery_knowledge', {'row': number, 'raw': row})
    stop = SOURCE / 'autorecover-20261004-163617-town-blocked-survival-mana-no-charges.bot-state-fixed.jsonl.gz'
    with gzip.open(stop, 'rt', encoding='utf8') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if row.get('turn') == 8795606 and row.get('knowledge', {}).get('category') == 'skill_exp':
                payload['recovery_knowledge'] = {'row': number, 'raw': row}
            if row.get('turn') == 8795606 and row.get('type') == 'player_turn':
                payload['boards']['8795606'] = {'row': number, 'raw': row}
    decisions = SOURCE / 'decisions-1441-1637.jsonl.gz'
    with gzip.open(decisions, 'rt', encoding='utf8') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if number in (576, 584, 662, 4140) or (
                row.get('turn') == 8795606 and row.get('reason') == 'town:blocked:survival-mana-no-charges'
            ):
                payload['decisions'].append({'row': number, 'raw': row})
    for path in (source, stop, decisions):
        payload['provenance'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert set(payload['boards']) == {'8795606'}
    TARGET.write_bytes(gzip.compress(json.dumps(payload, ensure_ascii=True).encode(), mtime=0))
    print('fixture', hashlib.sha256(TARGET.read_bytes()).hexdigest())
    for turn, board in payload['boards'].items():
        print(turn, board['row'], 'home', board.get('home', {}).get('row') if board.get('home') else None)


if __name__ == '__main__':
    extract()
