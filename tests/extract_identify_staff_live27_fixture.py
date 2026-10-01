"""Freeze live27 inputs by unique recorded turns; sources remain read-only."""
import gzip
import hashlib
import json
from pathlib import Path


def main():
    source = Path('C:/hengband/bot-client/jsonlog')
    stem = 'incident-20261001-0916-departure-unsatisfiable-identify-staff'
    decisions = [json.loads(line) for line in gzip.open(source / (stem + '.decisions.jsonl.gz'), 'rt', encoding='utf-8')]
    decisions = [row for row in decisions if 'decision_sequence' in row]
    assert [row['decision_sequence'] for row in decisions] == list(range(105))
    lines = list(gzip.open(source / (stem + '.state.jsonl.gz'), 'rt', encoding='utf-8'))
    rows = [json.loads(line) for line in lines]
    # CLI batch_bytes counts decoded characters, after universal-newline reading.
    cursor = max(i for i, row in enumerate(rows) if row.get('turn') == decisions[-1]['turn']) + 1
    ends = []
    for decision in reversed(decisions[1:]):
        ends.append(cursor - 1)
        size = 0
        while size < decision['timing']['batch_bytes']:
            cursor -= 1
            size += len(lines[cursor])
        assert size == decision['timing']['batch_bytes'], decision['decision_sequence']
        assert rows[ends[-1]]['turn'] == decision['turn']
    ends.append(cursor - 1)
    ends.reverse()
    assert rows[ends[0]]['turn'] == decisions[0]['turn']
    assert ends == sorted(set(ends))
    counts = [1] + [b - a for a, b in zip(ends, ends[1:])]
    output = Path(__file__).parent / 'fixtures' / 'identify-staff-live27.jsonl.gz'
    payload = ''.join(lines[ends[0]:ends[-1] + 1]).encode('utf-8')
    output.write_bytes(gzip.compress(payload, mtime=0))
    boundary = output.with_suffix('.boundaries.json')
    boundary.write_text(json.dumps({'input_rows': counts, 'recorded': decisions}, ensure_ascii=False) + '\n', encoding='utf-8')
    calibration = output.with_suffix('.calibration.json')
    calibration.write_bytes((source / 'character-calibration.json').read_bytes())
    provenance = {'sources': {name: hashlib.sha256((source / (stem + '.' + name)).read_bytes()).hexdigest() for name in ['state.jsonl.gz', 'decisions.jsonl.gz']}, 'attach_row': ends[0], 'end_row': ends[-1], 'decision_count': len(decisions), 'boundary_rule': 'walk backwards using exact current decision timing.batch_bytes decoded character count, verifying every turn; initial attach row alone'}
    output.with_suffix('.provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    for path in [output, boundary, calibration]:
        print(path.name, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
