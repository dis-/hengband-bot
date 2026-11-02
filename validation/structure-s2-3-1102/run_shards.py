"""Run replay_hold.py over a module list in parallel shards and join the rows.

usage: python run_shards.py <tree> <out.jsonl> <ids.txt> [<shards>] [--claim-row]
Modules are dealt round-robin, so a tree and its comparison tree get the same
shards.  Prints each shard's summary and the joined totals.
"""
import json
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
tree, out, ids = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
shards = int(sys.argv[4]) if len(sys.argv) > 4 else 10
flags = sys.argv[5:]
modules = [line.strip() for line in ids.read_text().splitlines() if line.strip()]
parts = [modules[index::shards] for index in range(shards)]
procs = []
for index, part in enumerate(parts):
    path = out.with_suffix(f'.{index}.jsonl')
    log = out.with_suffix(f'.{index}.log').open('w')
    procs.append((path, log, subprocess.Popen(
        [sys.executable, '-I', str(here / 'replay_hold.py'), *flags, tree, str(path), *part],
        stdout=subprocess.PIPE, stderr=log, text=True)))
totals = dict(tests=0, failures=0, errors=0, skipped=0)
with out.open('w', encoding='utf8', newline='\n') as joined:
    for path, log, proc in procs:
        summary, _ = proc.communicate()
        log.close()
        line = summary.strip().splitlines()[-1] if summary.strip() else '{}'
        print(path.name, line)
        for name, value in json.loads(line).items():
            totals[name] += value
        joined.write(path.read_text(encoding='utf8'))
print(json.dumps(totals))
