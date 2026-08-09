# Live coverage audit fix event

## 2026-08-10 initial decision-log audit

Command:

```text
py -3 scripts/live_coverage_audit.py jsonlog/evidence-double-recall-read.jsonl jsonlog/evidence-identify-staff-departure-loop.jsonl
```

The two logs contained 36 distinct reasons and 21 distinct composed key shapes. The audit reported these
17 distinct orphans (combined occurrence counts):

```text
ORPHANED key-shape "\x1b`n'." count=4
ORPHANED key-shape '5do\x1b' count=2
ORPHANED key-shape 'Cf\ry\x1b\x1b' count=13
ORPHANED key-shape '\x1b`n#.' count=10
ORPHANED key-shape '\x1b`n$.' count=4
ORPHANED key-shape '\x1b`n&.' count=6
ORPHANED key-shape 'pl\r' count=1
ORPHANED key-shape 'pm3\r\r' count=4
ORPHANED key-shape 'pq21\r\r' count=2
ORPHANED key-shape 'pq27\r\r' count=2
ORPHANED key-shape 'pq42\r\r' count=2
ORPHANED key-shape 'rha' count=2
ORPHANED key-shape '{n@0\r' count=2
ORPHANED reason shop:batch-sell count=15
ORPHANED reason shop:buy-healing count=1
ORPHANED reason shop:sale-inscription-unobserved-leave count=2
ORPHANED reason town:wait-restock:temple count=2
```

The exit status was 1, as required by the default zero-orphan gate.
