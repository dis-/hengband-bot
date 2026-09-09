# SOL-TASK: the receipt wrapper breaks the serial standing gate (exit 1, always)

The serial standing suite — the authoritative non-CLI gate — **cannot pass**. Every receipt-wrapped
run ends `exit_code 1` on the same error, regardless of the change under test. A gate that always
fails is a gate nobody can read, and it masks real regressions.

## Measured

Standing run at `a75bdb7` (receipt
`jsonlog/receipts/test_timing_runner-full-20260910T003404+0900.json`):

```
exit_code   1
test_count  3164
failures    0
errors      1  tests.test_emit_ownership.EmitOwnershipTest
                 .test_follow_and_retry_sites_log_their_own_populated_verdicts
```

Traceback (from that receipt's `.stderr.log`):

```
File "src\hengbot\cli.py", line 2631, in _run_follow
    _arm_decision_watchdog()
File "src\hengbot\cli.py", line 106, in _arm_decision_watchdog
    faulthandler.dump_traceback_later(
        DECISION_WATCHDOG_SECONDS, repeat=True, file=sys.stderr,
    )
io.UnsupportedOperation: fileno
```

## Root cause

`scripts/run_receipt.py:154` wraps the whole run:

```python
with contextlib.redirect_stdout(Tee(sys.stdout, out)), contextlib.redirect_stderr(Tee(sys.stderr, err)):
```

`Tee` (`run_receipt.py:134`) subclasses `io.TextIOBase` and defines only `write` and `flush`. It
inherits `io.TextIOBase.fileno()`, which raises `io.UnsupportedOperation`.
`faulthandler.dump_traceback_later(file=...)` requires a real file descriptor, so any test that
reaches `cli._run_follow` under the wrapper errors.

`scripts/test_timing_runner.py:197` re-invokes itself through `run_receipt.run_native(...)`, so the
serial suite always runs with `sys.stderr = Tee`.

**Why the parallel suite is green and the serial one is not**: `test_parallel_runner` runs its
shards in worker SUBPROCESSES, whose stderr is a real pipe with a real fd. Only the in-process
serial runner inherits the `Tee`.

## Proof it is the wrapper, not any change under test

Three independent checks, all run 2026-09-10:

1. The test passes **in isolation** without the wrapper: `python -m unittest <that test>` -> `OK`,
   1.009s.
2. The test fails **alone under the wrapper**, with no other module loaded:
   `python scripts/test_timing_runner.py --modules tests.test_emit_ownership`
   -> receipt `test_timing_runner-modules-20260910T012329+0900.json`, `exit_code 1`,
   11 tests, 0 failures, **the same 1 error**.
3. Run order rules out interference: the module list shows `test_emit_ownership` at order index 79
   and the six `town_producer_purity_part*` modules at 82-88 — the purity modules run **after** the
   failing test.

## What to fix

Give `Tee` a working `fileno()` that delegates to the underlying display stream, so
`faulthandler` and anything else needing a real descriptor keeps working while output is still
captured. If delegating is wrong for a reason you can demonstrate, the alternative is for
`_arm_decision_watchdog` to fall back safely when `sys.stderr` has no descriptor — but prefer
fixing the wrapper: the watchdog losing its output under a receipt is a real loss of diagnostics.

Whichever you choose, **the serial standing suite must end `exit_code 0`** at a commit where the
parallel suite is green. That is the acceptance condition.

## Hard requirements

- A pin must fail on a targeted production-only revert. Run the revert and name the test that
  actually failed, with its assertion.
- No new guard constant, latch, or budget.
- **The bot is RUNNING** (resumed 2026-09-10 01:24, PID 20984, game PID 17368). Do not stop it, do
  not touch the game, do not remove or create `jsonlog/maintenance.hold`. Be aware that a full
  suite throttles the single-threaded game about 4x while it runs.

## Operational limits — hard

1. Total memory across all processes you start: **under 16 GB**.
2. **Suites run SEQUENTIALLY.** Never two full suites at once.
3. `jsonlog` must stay **under 5 GB total** (currently 2.58 GB).
