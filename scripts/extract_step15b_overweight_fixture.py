"""Freeze the five overweight captures, preserving every recorded row."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--source-dir', type=Path, required=True)
parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] /
                    'tests/fixtures/step1.5b-overweight.json.gz')
args = parser.parse_args()
output = {}
for stamp in ('20261008-175411', '20261008-134816', '20261008-090841',
              '20261008-134200', '20261008-134643'):
    capture = {}
    for kind in ('bot-decisions', 'bot-state-fixed'):
        matches = list(args.source_dir.glob(f'autorecover-{stamp}*.{kind}.jsonl.gz'))
        if len(matches) != 1:
            raise ValueError((stamp, kind, matches))
        source = matches[0]
        raw = source.read_bytes()
        rows = [json.loads(line) for line in gzip.decompress(raw).decode('utf8').splitlines()]
        capture[kind] = {'source': source.name, 'sha256': hashlib.sha256(raw).hexdigest(),
                         'rows': rows}
    decisions = capture['bot-decisions']['rows']
    start = max((i for i, row in enumerate(decisions) if row.get('decision_sequence') == 1), default=0)
    capture['bot-decisions']['rows'] = decisions[start:]
    capture['decision_start_line'] = start + 1
    output[stamp] = capture
args.output.write_bytes(gzip.compress(json.dumps(output, ensure_ascii=True).encode(), mtime=0))
print(args.output, hashlib.sha256(args.output.read_bytes()).hexdigest())
