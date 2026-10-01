# Class C2 implementation and verification

The public recorded stop-board attachment now offers the already-approved
guardian fallback before `departure-unsatisfiable`, after the supply, deposit,
stockout and recovery producers have had their opportunity. Source change:
`src/hengbot/policy_town.py:5781-5800`; the existing safe picker and switch are
unchanged (`policy_helpers.py:324`, `policy_town.py:5157`, `policy.py:13723`).
No new threshold, attribute, screen classification, modal continuation or
equipment comparison was introduced. No requirement was lowered.

The refusal is Yeek cave 12F (dungeon 2). The real picker selects Orc cave
18F (dungeon 3): a deeper landing with no missing depth abilities and no
blocked guardian. The emitted public decision is `'1'`,
`town:entrance-step-off:town:unsafe-recall-fallback`; the normal surface
entrance wrapper steps off the Magic-shop entrance rather than posting WAIT
on that entrance. Its target is now 3 and the conquest latch is cleared.
No recall is posted. The next genuine board must still pass every departure
predicate. The old and new physical keys happen to be the same `'1'`; the
reason and policy target are the first difference. Replay stops there.

The weight answer is independently established: the recorded deposit removes
the pick, shovel and phase-door scroll (215 total), reducing 1983 to 1768.
The STR index 29 limit is 1750, so 18 excess remains. The live retained
quantities and the real selector leave no safe deposit. Five Identify staffs
at four charges each provide exactly the required 20. Home is 61/240, not
full. No additional overweight runtime change is warranted on that board.
The constructed extra-phase-scroll pin proves even a 5-weight surplus which
cannot clear the overload gets a Home route before the guardian switch.

The Home cycle was catalog work: recorded Home entrance is (45,123); '9'
steps off to (44,124), '1' re-enters, and the incomplete-page owner leaves
with ESC. Three no-effect catalog passes block Home. These are not failed
deposit effects. Step 1's direction description and its two stale terminal
line references have been corrected against the printed recorded positions
and e8824223 source. The full mapping is in `classC2-evidence.json`.

## Fidelity and fail-before/pass-after

`tests/test_classC2_departure_recorded.py` contains five pins. Its substrate
is `tests/fixtures/classC2-departure-20261001.json.gz`, extracted from the
read-only incident logs by `scripts/extract_classC2_departure.py` with source
hashes. This is a declared frozen seam: the incident has no pre-decision
pickle or serialized equipment catalog. Actual prior Home and skill
knowledge, shelves, purchase quantities, conquest latches and ledger are
attached to the exported outside board. The optimizer runs normally with
the calibration that predated this run; readiness and screens are not mocked.
The two observed digger deposits update the prior knowledge's catalog to the
recorded 40 equipment items. The optimizer finds a zero-action plan on the stop board. Historical boards
after a changed decision are never treated as effects of that decision.

`classC2-single-revert.txt` records:

- b24fd077 runtime content: public entry produces exactly `'1'`,
  `town:blocked:departure-unsatisfiable`, failed leaves
  `[inventory_weight_ready, recall_landing_not_guardian_blocked]`, target 2.
- One revert of the new town hunk to e8824223: the new module fails exactly
  the guardian-remedy and no-alternate pins by assertion. Three other pins
  pass. All five runtime files are restored byte-for-byte in `finally`.
- Final restored code: all five pins pass, including checkpoint restoration.
  The calibration is loaded before checkpointing so its isolated restored
  file path cannot lose the recorded calibration.

An early revert-script invocation hit an import/cache error, and another
needed the repository root on the probe's import path. Both restored files
in `finally`. The completed experiment uses an actual probe script and
separate temporary bytecode caches for each source version; its final log
above supersedes those incomplete attempts.

## Requested verification

Exactly the requested nine test modules were run, one module per process,
with normal Python313 and `PYTHONPATH=src;tests;scripts`.
**83 tests: 82 passed; one pre-existing fixture-hash failure.**

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_classC2_departure_recorded | 5 | pass |
| tests.test_classC_departure_remedies | 5 | pass |
| tests.test_live36_weight | 7 | 6 pass, 1 pre-existing SHA failure |
| tests.test_identify_staff_live27_recorded | 1 | pass |
| tests.test_departure_unsatisfiable_weight_recorded | 7 | pass |
| tests.test_guardian_recall_pingpong_recorded | 7 | pass |
| tests.test_town_progress_invariant | 22 | pass |
| tests.test_ownership_s2a_classification | 16 | pass |
| tests.test_test_fakery_lint | 13 | pass |

The enumerated guardian test module is exactly
`tests.test_guardian_recall_pingpong_recorded`. Per-module logs and counts
are in `classC2-tests.*.txt` and `classC2-result.json`.

The permitted stuck/withdraw fixture exception also passes:

| Fixture | OFF hash | S3.3 first difference | Trajectory defect |
| --- | --- | --- | --- |
| stuck | c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | none | none |
| withdraw | a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | (3,3,ESC,equipment-transaction:catalogue-leave-for-scan) | none |

OFF and S3.3 run separately; `EXPECTED_FIRST` is untouched. Their JSON
results are `classC2-{stuck,withdraw}-{off,s33}.json`.

The live36 failure occurs at `test_live36_weight.py:69`, before its remaining
frozen-fact assertions: actual SHA
`33558b2ac36f04cd57861c9cdcb3ec9aadccce4d28596cba99b58a5f874a2348`, expected
`b9d78eefbc220d7accb30eeb96433cae91414a45c94ff5dcce869addc9322ff3`.
The actual bytes are identical in the fixture's introducing commit e3adcc42,
the task baseline e8824223, and HEAD (`classC2-live36-preexisting-hash.json`).
Neither the fixture nor its assertion was changed. Its other six behavior
tests pass. The historical SHA/provenance inconsistency remains for Claude.

## Pending Claude work and limits

The imported DO-NOT-RUN work remains pending: `tests.test_cli`,
`tests.test_policy_town`, `tests.test_policy_shop`, `tests.test_absorbing_states`;
long tour/town/overweight replays; town-producer purity parts; full-fixture
first-divergence runs or matching-module sweeps; `scripts/test_parallel_runner.py`,
`scripts/test_timing_runner.py`, `scripts/hunk_guard.py`, `scripts/verify_scope.py`,
`scripts/mutation_battery.py`, and full-suite gates. None was run.

All changes are local to bot-client-c2. Game, live bot, executables, jsonlog,
other worktrees and existing assertions are untouched. The isolated fixture
and the report do not claim a subsequent successful live departure: residual
overweight with no safe surplus remains a legitimate hard gate.

changed_preexisting_assertions: []

assertion_audit (verbatim, base e8824223):

```
No changed pre-existing assertions or forbidden test edits.
```

Step 1 commit: `1a61d10b`. Implementation and final report commit IDs are
recorded in the final result event and user response.
