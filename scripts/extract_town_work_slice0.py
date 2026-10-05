"""Freeze slice-0 capture evidence; backups are read-only, no game/bot input.

Captures lack policy checkpoints and start inside a JSON record. Every complete
town/store board is retained for INDEPENDENT reconstructed-board observer controls,
not a continuous historical replay. Recorded decision rungs are retained separately
to reconcile producers even where the state tail no longer contains their board.
"""
import gzip
import hashlib
import json
from pathlib import Path
from hengbot.protocol import BOARD_SNAPSHOT_TYPES

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = Path('C:/hengband-backups/state-logs')
NAMES = ('crosstown-loop-20261006-0355', 'home-full-nosurplus-20261005-2356')
OUTPUT = ROOT / 'tests/fixtures/town-work-slice0-captures-20261006.json.gz'


def rows(path):
    for number, raw in enumerate(path.read_bytes().splitlines(), 1):
        try:
            yield number, json.loads(raw)
        except (UnicodeDecodeError, ValueError):
            # A tail begins inside a record; preserve the physical line gap.
            yield number, None


def main():
    captures = []
    for name in NAMES:
        directory = BACKUPS / name
        sources = {filename: hashlib.sha256((directory / filename).read_bytes()).hexdigest()
                   for filename in ('bot-decisions.jsonl', 'bot-state-tail.jsonl')}
        decisions = []
        for physical, row in rows(directory / 'bot-decisions.jsonl'):
            if row is None:
                continue
            floor = row.get('floor') or {}
            if not (floor.get('dungeon_id') == 0 and floor.get('level') == 0
                    or row.get('store_type') is not None):
                continue
            claim = row.get('claim') or {}
            decisions.append(dict(physical_row=physical, sequence=row.get('decision_sequence'),
                                  turn=row.get('turn'), key=row.get('key'), reason=row.get('reason'),
                                  rung=claim.get('rung'), execution=claim.get('execution'),
                                  store_type=row.get('store_type')))
        boards = []
        response_rows = []
        skills = []
        skill_baseline = None
        town_identity = None
        skipped = []
        total = 0
        for physical, row in rows(directory / 'bot-state-tail.jsonl'):
            total = physical
            if row is None:
                skipped.append(physical)
                continue
            floor = row.get('floor') or {}
            identity = (floor.get('town_id'), row.get('player', {}).get('level'))
            if row.get('type') in BOARD_SNAPSHOT_TYPES:
                if not floor.get('in_town') or identity != town_identity:
                    skill_baseline = None
                town_identity = identity
            knowledge = row.get('knowledge') or {}
            if row.get('type') == 'knowledge' and knowledge.get('category') == 'skill_exp':
                skills.append(dict(physical_row=physical, data=dict(knowledge=knowledge,
                              player=dict(level=row['player']['level']))))
                skill_baseline = len(skills) - 1
            if row.get('floor', {}).get('in_town') or row.get('store') is not None:
                if row.get('type') in BOARD_SNAPSHOT_TYPES:
                    boards.append(dict(physical_row=physical, board=row, skill_baseline=skill_baseline))
                else:
                    response_rows.append(dict(physical_row=physical, type=row.get('type'),
                                              sha256=hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()))
        captures.append(dict(name=name, sources=sources, decisions=decisions,
                             boards=boards, state_physical_rows=total, skipped_partial_rows=skipped,
                             non_board_town_responses=response_rows,
                             skill_knowledge=skills,
                             checkpoint='absent; all board controls reconstruct baseline independently',
                             replay_boundary='never deliver a later historical response after divergence'))
    data = dict(schema=1, design='town-progress/slice0', captures=captures,
                board_controls='independent observation controls; not historical continuation proof')
    payload = (json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    OUTPUT.write_bytes(gzip.compress(payload, mtime=0))
    for capture in captures:
        print(f'{capture["name"]}: {len(capture["decisions"])} recorded town/store decisions; '
              f'{len(capture["boards"])} complete town/store boards; '
              f'{len(capture["non_board_town_responses"])} non-board response rows; '
              f'partial rows {capture["skipped_partial_rows"]}')
    print(f'fixture sha256={hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
