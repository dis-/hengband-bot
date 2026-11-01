"""Compare two replay_choose_key.py outputs decision by decision.

usage: python compare_replays.py <main.jsonl> <branch.jsonl>
Prints the decision count, the number of tests, and every differing decision
(test id, ordinal, both rows). Exit 1 when any decision differs.
"""
import json
import sys


def load(path):
    rows = {}
    with open(path, encoding='utf8') as stream:
        for line in stream:
            test, ordinal, *rest = json.loads(line)
            rows[(test, ordinal)] = rest
    return rows


main, branch = (load(path) for path in sys.argv[1:3])
differ = sorted(k for k in main.keys() | branch.keys() if main.get(k) != branch.get(k))
receipts = sum(len(row[2]) for row in main.values())
print(json.dumps(dict(decisions_main=len(main), decisions_branch=len(branch),
                      tests=len({test for test, _ in main}), receipts=receipts, differing=len(differ))))
for key in differ[:20]:
    print(key, '\n  main  ', main.get(key), '\n  branch', branch.get(key))
raise SystemExit(1 if differ else 0)
