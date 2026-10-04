"""Freeze parked hold boards, not a reconstructed lifetime replay.

The onset boards were rotated out of state.jsonl.gz.  Keep the first 80
preserved boards (over 500 game turns), their exact decision rows, and the
onset decision. Tests declare the already-active retreat state explicitly.
Read only the backup; never access the live jsonlog.
"""
import gzip
import json
from pathlib import Path

SOURCE = Path('C:/hengband-backups/state-logs/choke-hold-loop-20261005-0611')
OUTPUT = Path(__file__).parent / 'fixtures/choke-hold-loop-20261005.jsonl.gz'


def main():
    decisions = {}
    for name in ('decisions-1.jsonl.gz', 'decisions.jsonl.gz'):
        with gzip.open(SOURCE / name, 'rt', encoding='utf-8') as stream:
            for line_number, line in enumerate(stream, 1):
                row = json.loads(line)
                decisions[row['turn']] = (name, line_number, row)
    records = []
    name, line_number, row = decisions[10457786]
    records.append(dict(role='onset', source=name, line_number=line_number,
                        decision=row))
    with gzip.open(SOURCE / 'state.jsonl.gz', 'rt', encoding='utf-8') as stream:
        for line_number, line in enumerate(stream, 1):
            if line_number > 80:
                break
            board = json.loads(line)
            name, decision_line, decision = decisions[board['turn']]
            records.append(dict(role='board', source='state.jsonl.gz',
                                line_number=line_number, board=board,
                                decision_source=name, decision_line=decision_line,
                                decision=decision))
    with gzip.GzipFile(filename=str(OUTPUT), mode='wb', mtime=0) as stream:
        stream.write(''.join(json.dumps(r, ensure_ascii=False) + '\n'
                             for r in records).encode('utf-8'))
    print(f'{OUTPUT}: {len(records)-1} boards, '
          f"{records[1]['board']['turn']}..{records[-1]['board']['turn']}")


if __name__ == '__main__':
    main()
