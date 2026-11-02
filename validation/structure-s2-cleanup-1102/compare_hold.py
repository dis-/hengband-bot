"""Compare two replay_hold.py outputs decision by decision.

usage: python compare_hold.py <main.jsonl> <branch.jsonl> [--deleted f1,f2] [--drop-claim-row] [--common-tests] [--map OLD=NEW] [<dropped test id prefix> ...]
--map rewrites a module prefix in the branch's rows before comparing (a
moved function's site name, e.g. town_hold.py:=town_terminal.py:); the number
of rewritten rows is printed.
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
# --drop-claim-row: leave out the whole-decision_claim column of a side run
# with --claim-row (for a step that deletes the decision_claim row).
drop_claim_row = args[:1] == ['--drop-claim-row']
if drop_claim_row:
    args = args[1:]
# --common-tests: compare only the tests present on both sides (a step that
# deletes or renames tests); the one-sided test ids are listed.
common_tests = args[:1] == ['--common-tests']
if common_tests:
    args = args[1:]
mapping = None
if args[:1] == ['--map']:
    mapping, args = tuple(args[1].split('=', 1)), args[2:]
mapped = {'rows': 0}


def load(path, dropped):
    rows = {}
    with open(path, encoding='utf8') as stream:
        for line in stream:
            if mapping is not None and path == sys.argv[2] and mapping[0] in line:
                line = line.replace(mapping[0], mapping[1])
                mapped['rows'] += 1
            test, ordinal, *rest = json.loads(line)
            if drop_claim_row and len(rest) == 7:
                del rest[5]
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
if common_tests:
    main_tests, branch_tests = {t for t, _ in main}, {t for t, _ in branch}
    shared = main_tests & branch_tests
    print(json.dumps(dict(only_main=sorted(main_tests - shared), only_branch=sorted(branch_tests - shared))))
    main = {k: v for k, v in main.items() if k[0] in shared}
    branch = {k: v for k, v in branch.items() if k[0] in shared}
differ = sorted((k for k in main.keys() | branch.keys() if main.get(k) != branch.get(k)), key=repr)
print(json.dumps(dict(
    mapped_rows=mapped['rows'],
    decisions_main=sum(o not in ('end', 'outcome') for _, o in main),
    decisions_branch=sum(o not in ('end', 'outcome') for _, o in branch),
    outcomes_main=sum(o == 'outcome' for _, o in main), outcomes_branch=sum(o == 'outcome' for _, o in branch),
    tests=len({test for test, _ in main}), receipts=sum(len(row[2]) for row in main.values()),
    hold_calls=sum(len(row[-1]) for row in main.values()),
    deferred_rows=sum(row[4] not in ('None', '[]') for row in main.values()), differing=len(differ))))
for key in differ[:20]:
    print(key, '\n  main  ', main.get(key), '\n  branch', branch.get(key))
raise SystemExit(1 if differ else 0)
