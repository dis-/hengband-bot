"""Offline reconstruction of the copied October 5 full-Home incident.

This is a suffix replay, not a checkpoint of the original live process.
All responses pass through the existing recorded-replay consumption helper.
"""
import tests  # isolate runtime files before policy imports
import argparse
import base64
import cProfile
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import pstats
from tempfile import TemporaryDirectory
import time

from hengbot.cli import _consume_response_sequence, _request_due_dump
from hengbot.latch_onset_capture import checkpoint
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy


def replay(source, output=None, start_row=37, *, profile_final=True):
    monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')
    lines = gzip.decompress(source.read_bytes()).decode('utf-8-sig').splitlines()
    decisions = []
    with TemporaryDirectory() as raw:
        directory = Path(raw)
        policy = _policy(directory, monrace)
        # This suffix contains its own equipped character response. Do not
        # substitute the older ESP fixture's calibration for that observation.
        policy._character_calibration_path.unlink()
        policy._crossarea_fundraising_enforced = True
        policy._in_store_ops_enabled = True
        _request_due_dump(policy, 0, 0)
        for index in range(start_row, len(lines)):
            line = lines[index]
            _, snapshots = _consume_response_sequence(
                [line], policy, lambda _key: True, monrace,
                knowledge_ledger_path=directory / 'knowledge.jsonl')
            if not snapshots:
                continue
            # Rows 40 and 42 are downstream operation observations, not new
            # policy inputs in the recorded driver window.
            if index in {40, 42}:
                continue
            snapshot = snapshots[-1]
            if index == start_row:
                policy.prime(snapshot)
            snapshot = policy.with_known_skill_exp(snapshot)
            policy.observe_store_screen(snapshot.store is not None)
            frozen = None
            if index == 53:
                frozen = dict(
                    construction='Offline suffix replay, not live checkpoint; '
                    'recorded responses consumed through _consume_response_sequence',
                    source=source.name, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    start_row=start_row, source_row=index,
                    policy=checkpoint(policy),
                    snapshot=base64.b64encode(pickle.dumps(snapshot, protocol=5)).decode('ascii'))
            profile = cProfile.Profile()
            started = time.thread_time()
            key = (profile.runcall(policy.choose_key, snapshot)
                   if frozen and profile_final else policy.choose_key(snapshot))
            elapsed = time.thread_time() - started
            row = dict(row=index, turn=snapshot.turn, key=key, reason=policy.last_reason, elapsed=elapsed)
            decisions.append(row)
            print(json.dumps(row), flush=True)
            if frozen and output is not None:
                profile.dump_stats(str(output.with_suffix('.prof')))
                with output.with_suffix('.profile.txt').open('w', encoding='utf-8') as stream:
                    pstats.Stats(profile, stream=stream).sort_stats('cumulative').print_stats(25)
                frozen['decisions'] = decisions
                output.write_bytes(gzip.compress(json.dumps(frozen).encode(), mtime=0))
            if key:
                policy.confirm_key_posted(key)
    return decisions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--start-row', type=int, default=37)
    args = parser.parse_args()
    replay(args.source, args.output, args.start_row)
