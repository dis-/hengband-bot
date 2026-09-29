# S3.3 R7: review steps 3, 4, and 4b

This round changes records and tests only. It leaves the S3.3 ON selection
rules for the later behavior step. The local game and live bot were not run.

## Step 3: leave barrier provenance

`policy.py:3054` resolves both leave waits from the visit's captured operation
family, then its selected `exit_requester` if that requester belongs to the
visit's requester set. Missing evidence records `barrier-provenance-missing`.
The same resolver feeds decision attribution, claim ownership, the final hold
family, and claim telemetry (`policy.py:2944`, `:3068`, `:4126`, `:4497`).
`town_arbiter.py:884` captures the selected exit requester once. A completed
operation's exit no longer opens a fresh store-operation Observe
(`policy.py:3611`, `:3630`). Both barrier reasons, completed effect, immutable
exit selection, and older restored visits are pinned in
`tests/test_ownership_s3a_record.py`. The recorded town approach at sequence
1958 lacks captured operation provenance and now records
`barrier-provenance-missing`, pinned in
`tests/test_town_approach_retired_recorded.py`. An older unobserved leave
capture also lacks provenance; its original shop-buy closing remains pinned
when that operation family is supplied explicitly in
`tests/test_ownership_s2a1_closure.py`.

Commit: `1e8c339a`; restored-visit pin and compatibility follow-ups
`b5429663`, `8c24e9a3`, `75e4732d`; recorded pins `ef93a790`,
`116e13a9`.

## Step 4: entry probes and reservation binding

The identification, curse-enchant, and cross-town producers now ask
`_claim_errand_hold` on entry (`policy.py:10108`,
`policy_equipment.py:2189,2722`, `policy_quest.py:1302`,
`policy_shop.py:1406`, `policy_town.py:1800,4222`); the rumor branch asks
before selecting its key (`policy_town.py:4935`). These are record-only probes.
Every execution delegation now starts as a named reservation at its opening
site, including calibration session installation; the `choose_key` claim exit
binds a matching owner or cancels the reservation by name
(`policy.py:5221,5255`). A reservation left behind by a decision that missed
its claim exit is cancelled at the next public decision (`policy.py:2480`).
Tests cover actual session installation, matching
and mismatched exits, no claim exit, missed exit, and all four producer families in
`tests/test_ownership_s3_3_delegation_record.py`.

Commits: `01f98c0d`, `8e8fc237`. Step 4b diagnosis is
[`s3-early-divergence-causes.md`](s3-early-divergence-causes.md).

## OFF identity and first ON difference

Both step 3 and step 4 ran `scripts/first_divergence_s3_3.py`, one fixture per
process. All six OFF key/reason hashes equal their R4 pins. Each first
difference below is identical after both steps; no first divergence got worse.
`ESC` = `\x1b`, `CR` = `\r`.

| Fixture | OFF SHA-256 | First index | OFF key / reason | ON key / reason |
| --- | --- | ---: | --- | --- |
| Tour | `d30b053bc9744336253c0b2235f7887dd3b4604bc09a86b715262c8377de5464` | 2643 | `~9 ESC` / `home:request-knowledge-scan` | `ESC` / `home:scan-incomplete-open-page` |
| Town approach | `7fe5100909a3346355e5c0a9c4e66d649bae412987a46276040c077277f550b1` | 1179 | `ESC` / `home-errand:filed:combat-weapon` | `ESC` / `home:store-context-exit` |
| Overweight Home | `8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b` | 6 | `~9 ESC ESC` / `home:request-knowledge-scan` | `ESC` + travel macro / `shop:travel` |
| Home withdraw | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | 3 | `~9 ESC` / `home:request-knowledge-scan` | `5` / `ownership:holder-complete` |
| Recall cancel | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` | none | same throughout | same throughout |
| Stuck prompt | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | none | same throughout | same throughout |

## ON token admissions

Full ON replay counts use `scripts/measure_s3_3_on.py`. The step 3 values are
replayed with its original immediate-parent binding restored in a process;
the step 4 values use committed binding. Entry probes have no return-value
effect. These counts are record-only and do not admit tokens to ON dispatch.

| Fixture | Step 3 admissions / deferrals | Step 4 admissions / deferrals |
| --- | ---: | ---: |
| Tour | 8 / 292 | 8 / 292 |
| Town approach | 0 / 79 | 0 / 79 |
| Overweight Home | 0 / 148 | 0 / 148 |

All 8 tour admissions are calibration to equipment transaction. The named
real interruptions have zero token admissions. The step 3 and final ON stream
hashes are identical in all three measured replays: tour
`13f496c8528fb6e9c301d242bab1c01248c05b9453d715c94165a13432b09f8b`,
town `76d66581470b9e4c1fc724397bcfcbeeceeb8868b7b24555059ff1a2b10f28ba`,
and overweight `e77d79df4161f8f57b7237ff0c04d5460edee791844854088280654b0ed140f7`.

## Required modules

The HARD RULES set ran as 125 modules, one Python process per module:
**4,049 tests passed, 0 final failures**. Exact per-module counts are in
`s3-r7-test-counts.tsv`; `test_town_stall` discovers 0 tests. Three modules
initially found restored-visit or older inferred-provenance pins; after the
corresponding fixes, full-module reruns passed:
`test_home_entry_capture` (8), `test_ownership_s2a1_closure` (80), and
`test_town_approach_retired_recorded` (8). The count file records their final
passing results.
