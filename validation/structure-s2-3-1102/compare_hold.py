"""Compare two replay_hold.py outputs decision by decision.

usage: python compare_hold.py <main.jsonl> <branch.jsonl> [--deleted f1,f2] [<dropped test id prefix> ...]
Hold and defer calls with a deleted function among their four nearest callers
(record-only code the branch deleted) are left out of both sides, and the
caller names are not compared; tests whose id starts with a given prefix (tests
deleted on the branch) are left out.  Prints the counts and the first differing rows; exit 1 on any
difference.
"""
import json
import sys


args = sys.argv[3:]
deleted = set()
if args[:1] == ['--deleted']:
    deleted, args = set(args[1].split(',')), args[2:]


def load(path, dropped):
    rows = {}
    with open(path, encoding='utf8') as stream:
        for line in stream:
            test, ordinal, *rest = json.loads(line)
            if test.startswith(dropped):
                continue
            rest[-1] = [call[:-1] for call in rest[-1] if not deleted & set(call[-1])]
            if ordinal == 'end':
                # A test's own probes after its last decision often walk a set
                # (string hashing differs per process): compare them unordered.
                rest[-1] = sorted(rest[-1], key=lambda call: json.dumps(call, default=repr))
            if ordinal == 'end' and not rest[-1]:
                continue
            rows[(test, ordinal)] = rest
    return rows


dropped = tuple(args) or ('\0',)
main, branch = (load(path, dropped) for path in sys.argv[1:3])
differ = sorted((k for k in main.keys() | branch.keys() if main.get(k) != branch.get(k)), key=repr)
print(json.dumps(dict(
    decisions_main=sum(o != 'end' for _, o in main), decisions_branch=sum(o != 'end' for _, o in branch),
    tests=len({test for test, _ in main}), receipts=sum(len(row[2]) for row in main.values()),
    hold_calls=sum(len(row[-1]) for row in main.values()),
    deferred_rows=sum(row[4] not in ('None', '[]') for row in main.values()), differing=len(differ))))
for key in differ[:20]:
    print(key, '\n  main  ', main.get(key), '\n  branch', branch.get(key))
raise SystemExit(1 if differ else 0)
