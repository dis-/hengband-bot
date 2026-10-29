"""Freeze #47 high-level retirement boundaries from immutable local captures.

Only complete gzip members and complete JSON lines are read. No board fields
are edited. The diagnostic window includes the actual work and retirement
receipts; the final store refusal and surface boards support attach replays.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from extract_overweight_recurrence_1027 import ring_rows

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = Path('C:/hengband-backups/viewing-captures-1029/top24')
CASES = (('218', '050930'), ('218', '062121'), ('218', '062134'),
         ('218', '062910'), ('218', '062929'), ('221', '063340'),
         ('225', '083759'), ('225', '084926'))


def extract():
    cases = []
    for life, stamp in CASES:
        source = next((CAPTURES / f'life-{life}/incident-captures').glob(f'*{stamp}*'))
        tail = source / 'decision-tail.jsonl'
        decisions = []
        for line in tail.read_bytes().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if 'decision_sequence' in row:
                decisions.append(row)
        window = decisions[-70:]
        turns = {row['turn'] for row in window}
        ring = source / 'snapshots/snapshots-current.jsonl.gz'
        boards = {}
        knowledge = {}
        for row in ring_rows(ring):
            if row['type'] == 'knowledge':
                knowledge[row['knowledge']['category']] = row
            elif row['type'] in {'player_turn', 'store'} and row['turn'] in turns:
                identity = (row['turn'], row['player']['y'], row['player']['x'],
                            row.get('store', {}).get('store_type'))
                boards[identity] = row
        fixed = stamp in {'062121', '083759', '084926'}
        wanted = [window[-1]]
        if fixed:
            wanted.insert(0, next(row for row in reversed(window)
                                  if row['reason'] == 'policy:none-store-exit'))
        inputs = []
        for row in wanted:
            identity = (row['turn'], row['position']['y'], row['position']['x'],
                        row['store_type'])
            inputs.append({'decision': row, 'board': boards[identity]})
        dump = json.loads((source / 'policy-state.json').read_bytes())
        receipts = [{k: r.get(k) for k in ('turn', 'reason', 'key', 'position',
                    'store_type', 'claim', 'town_idle_d0', 'descent_refusal',
                    'procurement_requirements', 'departure_block')}
                    for r in window if (r.get('town_idle_d0') or {}).get('trigger_category')]
        case = {'source': f'life-{life}/{source.name}', 'fixed_group': fixed,
                'inputs': inputs, 'knowledge': knowledge, 'retirements': receipts,
                'window': [{k: r.get(k) for k in ('turn', 'reason', 'key', 'position',
                           'store_type', 'equipment_mutation_report')}
                           for r in window],
                'policy_state': dump,
                'sha256': {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in (tail, ring, source / 'policy-state.json')}}
        if fixed:
            case['transaction_claim'] = next(r['claim'] for r in reversed(window)
                if (r.get('claim') or {}).get('owner') == 'equipment-txn'
                and r['claim']['goal'].get('source') == 'transaction')
        cases.append(case)
        print(case['source'], 'level', inputs[-1]['board']['player']['level'], flush=True)
    output = ROOT / 'tests/fixtures/retired-burst-high-20261029.json.gz'
    output.write_bytes(gzip.compress(json.dumps(cases, ensure_ascii=False).encode('utf-8'), mtime=0))


if __name__ == '__main__':
    extract()
