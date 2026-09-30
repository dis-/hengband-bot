# S3.3 OFF shadow verdict

Implemented in `decl-r3b`, based on `b3be3f24`. Default S3.3 remains OFF.

## Fields and computation

Every town/store decision recorded with S3.3 OFF carries `s33_shadow` both
inside `claim` and at the top of the CLI decision row.

| Field | Meaning |
| --- | --- |
| `would_stop` | Typed ON admission/holder-resolution stop, or null |
| `would_skip_families` | Sorted, unique families refused by the ON entry predicates on the decided board |
| `holder_family`, `holder_claim_id` | Live holder after observed completions; the decided claim when no previous holder remains |
| `declaration_state` | Holder/decided execution state, or null |
| `declaration_gap` | Holder/decided claim has no execution declaration |
| `mismatch` | Existing declaration mismatch object, or null |

The recorder invokes the pure verdict at `src/hengbot/policy.py:4372`, after
its existing observed-completion pass and before it consumes execution offers
or declares the winner. `_s33_shadow_verdict` is at `policy.py:6648`; row
attachment is at `policy.py:4941`; CLI projection is at `src/hengbot/cli.py:903`.

Shared ON/OFF predicates: entry deferral `policy.py:5763`, plan admission
`policy.py:5822`, declaration identity and structural validity
`policy.py:6167` / `policy.py:6184`, unrestored debt `policy.py:6707`, and final
posted-operation/entry validity `policy.py:6728`. Exemptions use the existing
`_town_gate_exempt`. Holder lookup accepts an explicit enforcement argument;
shadow never toggles the policy switch. Delegation-token lookup reads old
checkpoints without installing missing attributes. No producer is called by
the shadow, and no new checkpoint attribute was introduced.

## Verification

One module per process, with the Codex runtime Python and
`PYTHONPATH=src;tests;scripts`:

| Module | Tests | Result |
| --- | ---: | --- |
| `tests.test_s33_shadow` | 7 | PASS |
| `tests.test_s33_shadow_report` | 2 | PASS |
| `tests.test_s33_shadow_recorded` | 6 | PASS |
| `tests.test_declarations_r11` | 10 | PASS |
| `tests.test_live8` | 11 | PASS |
| `tests.test_town_producer_purity_part1` | 1 | PASS (339.066 s) |
| `tests.test_test_fakery_lint` | 13 | PASS |

The pure-verdict pins compare serialized policy state before/after computing
the shadow, including restored checkpoints, a missing delegation attribute,
active bars, restoration debt, and missing/stale/silent holders. The entry
pin proves OFF calls its producer exactly once. The observed-arrival pin
prevents a completed route from being counted as a live gate leak.

Recorded comparisons cover live8 debt/one-shot identity, live9 capture,
live10 observed/stale restoration, live11 posted shop identity/changed store,
and the live13/live15 identification composer. Each compares OFF shadow with
the actual ON enforcement or holder dispatcher and checks both fresh and
pickle-restored policy state. The six fixture pin consumes only the first
input boundary (the declared closing-window boundary for stuck), including
captured attach skill knowledge when present. These are isolated attachment
checks, not full lifetime replays.

Single revert check: replace only `_record_decision_claim` in memory with the
method from `b3be3f24`, then run the new public-row pin. It fails exactly once
because `s33_shadow` is absent; the original method is restored in `finally`.
No source file or live process was changed by that check.

### OFF hashes and ON fixture results

The six frozen full-stream hashes remain unchanged in
`scripts/first_divergence_s3_3.py`. Only the two permitted full fixture
measurements were freshly executed:

| Fixture | Frozen OFF SHA-256 | Verification here |
| --- | --- | --- |
| tour | `d30b053bc9744336253c0b2235f7887dd3b4604bc09a86b715262c8377de5464` | First input-boundary pin only |
| town | `7fe5100909a3346355e5c0a9c4e66d649bae412987a46276040c077277f550b1` | First input-boundary pin only |
| overweight | `8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b` | First input-boundary pin only |
| withdraw | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | Fresh OFF + S3.3, 34 OFF rows |
| recall | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` | First input-boundary pin only |
| stuck | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | Fresh OFF + S3.3, 4 OFF rows |

stuck ON: no divergence. withdraw ON: first divergence at list index 20,
historical sequence 20, `shop:travel`, matching the unchanged `EXPECTED_FIRST`.
Both report `trajectory_defect: null`. Exact outputs are retained in
`validation/s33-shadow-{stuck,withdraw}-{off,s33}.json`.
The other four full streams were not rerun under the prompt's DO NOT RUN rule;
this report does not claim fresh full-stream identity evidence for them.

## Live report usage

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts/s33_shadow_report.py DECISIONS --start 2026-10-01T00:00:00Z --end 2026-10-01T02:00:00Z
```

The window is half-open. Add `--json` for structured output. It reports window
minutes, all decision rows, shadow rows, stop counts by reason/holder family,
first sequence/time for each distinct reason/family/producer-reason triple,
declaration gaps/mismatches by family, gate leaks, and per-family skip counts.
Rows without shadows are counted separately; a partial final JSON line is ignored.

Executable synthetic example:

```powershell
python scripts/s33_shadow_report.py validation/s33-shadow-sample.jsonl --start 2026-10-01T00:00:00Z --end 2026-10-01T00:05:00Z
```

```text
minutes=5 decisions=3 shadow_decisions=3
would_stop ownership:gate-missing:rumor holder=home-visit count=2
first ownership:gate-missing:rumor holder=home-visit producer=town:rumor-batch sequence=101 time=2026-10-01T00:01:00Z
declaration_gaps={"home-visit": 1}
mismatches={"home-visit": 1}
gate_leaks={"rumor": 2}
would_skip={"rumor": 3, "shop-buy": 2}
```

## Commits

1. `1121c4fe` — pure OFF town shadow verdict and basic/checkpoint pins.
2. `0d961a5e` — window report and synthetic aggregation pins.
3. The commit containing this report — recorded ON-equivalence pins,
   observed-completion placement, final validation artifacts, and sample log.

The live bot, game, executable, other worktrees, `jsonlog`, `EXPECTED_FIRST`,
and the pre-existing untracked `.live8b-revert.py` were not changed.
