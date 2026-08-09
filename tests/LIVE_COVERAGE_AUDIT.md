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

## 2026-08-10 depth-first optimization fix event

The unconstrained equipment selector now evaluates the requirement-free optimum
first, then considers the 81, 50-80, 40-49, 31-39, 26-30, 21-25, 20, and
requirement-free 19 bands in descending order.  Each satisfying band is adopted
only when its melee output is at least one half of the free optimum; zero free
melee uses ability-only classification.  The result and live policy telemetry
record every considered band with set existence, band melee, free melee, ratio,
and `no-set` or `melee-ratio` refusal, plus the chosen band and ratio.

Known-flags-only evidence remains authoritative.  The optimizer equivalence key
now retains the known depth-gate flag set so a metric-equivalent FA/rConf item is
not erased before band descent.  The live-catalogue regression records the base
result in its docstring: `dee4194 classified this catalogue at 19`; the fixed
selector derives 25 while retaining the rFire katana.

Pins added in `tests/test_equipment_optimizer.py` cover the live catalogue,
one-band retry after an 81-band melee-ratio refusal, requirement-free termination,
zero-melee ability classification, and every-band telemetry.

Scenario transfer: no old depth/classification test was deleted, renamed, or
changed.  All old scenarios remain in their original tests; the five new scenarios
live in the five depth-descent tests named above.

The live coverage command used the standing evidence pair because the default
evidence glob encountered a pre-existing UTF-8 BOM.  It reported these 16 orphans:

```text
key-shape "\x1b`n'."; key-shape '5do\x1b'; key-shape 'Cf\ry\x1b\x1b';
key-shape '\x1b`n#.'; key-shape '\x1b`n$.'; key-shape '\x1b`n&.';
key-shape 'd0\r'; key-shape 'pl\r'; key-shape 'pm3\r\r';
key-shape 'pq21\r\r'; key-shape 'pq27\r\r'; key-shape 'pq42\r\r';
key-shape '{n@0\r'; reason shop:buy-healing;
reason shop:sale-inscription-unobserved-leave;
reason town:wait-restock:temple
```
