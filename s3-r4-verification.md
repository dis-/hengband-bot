# Ownership S3.3 R4 verification

The S3.3 town claim bar is controlled by `_town_claim_bar_enforced` and remains
off by default. The ON replay measurements use the recorded ownership harnesses,
one replay per Python process. Decision numbers refer to those fixed captures.

## Steps and four preparatory assertions

1. Merged main `1fc93933` as `1dea0b66`.
2. Re-pinned the four effects of preparatory commit `50e36242` as `ea7fac32`:

   | Assertion | Cause and decision |
   | --- | --- |
   | Overweight Home visit owner mismatches 4 → 5 | Adopted (c') knowledge-source observation adds one genuine Home-scan requester/operator disagreement. Re-pinned 5. |
   | `test_policy_town` p4 character dump → key `6`, `town:entrance-step-off:shop:approach` | Adopted (a') gates the departure dump on `_periodic_filler_is_safe` even with the S3.3 switch OFF. Re-pinned the exact key/reason. This un-switched change affects that synthetic recorded-board assertion; none of the six full recorded key/reason streams below changed. |
   | Tour retarget at decision 3035 | Adopted (c') types calibration knowledge as `Observe(knowledge)`, exposing the same-family retarget. Added the exact S3 row. |
   | Tour Home knowledge completions 8 → 11 | Adopted (c') lets three suspended knowledge requests complete when the catalogue becomes current. Re-pinned 11. |

3. Implemented the ON town bar, holder continuation and visible silent-holder stop,
   store operation identity, requester attribution, and survival suspension for
   town claims. The recorded and class pins are in `test_ownership_s3a_record`.

## OFF identity

All six key/reason stream SHA-256 hashes equal their main-base streams:

| Replay | Decisions | SHA-256 |
| --- | ---: | --- |
| Tour | 4267 | `d30b053bc9744336253c0b2235f7887dd3b4604bc09a86b715262c8377de5464` |
| Town approach | 2052 | `7fe5100909a3346355e5c0a9c4e66d649bae412987a46276040c077277f550b1` |
| Overweight Home | 3782 | `8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b` |
| Home withdraw | 34 | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` |
| Recall cancel | 18 | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` |
| Stuck prompt | 4 | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` |

The 2026-09-26/27 incident capture modules in `s3-r4-test-counts.tsv` also pass.

## ON measurements

| Replay | S3 gate violations | `errand_deferred` | Holder-silent decisions | New stops or loops |
| --- | ---: | ---: | ---: | --- |
| Tour | 0 | 292 | 4 | Equipment Home route unavailable at 2656; owner-retired at 2723–2735; four visible calibration holder-silent stops at 3007/3034/3039/3049; calibration-required at 3065 and 4257/4259/4261. |
| Town approach | 0 | 79 | 0 | None. Existing equipment transaction stop at 1182 remains. |
| Overweight Home | 0 | 148 | 0 | None. |
| Home withdraw | 0 | 4 | 0 | None. |
| Recall cancel | 0 | 0 | 0 | None. |
| Stuck prompt | 0 | 0 | 0 | None. |

The tour harness continues feeding recorded boards after ON keys diverge. Thus
the later repeated owner-retired and calibration-required rows are visible
static-replay outcomes; they do not establish a live loop. The four
holder-silent rows are visible stops with an active calibration session but no
pending action, and those claims later expire.

`ESC` below denotes byte `\x1b`; `CR` denotes byte `\r`. Empty quotes denote
an empty key.

| Replay:decision | Recorded key / reason | ON key / reason |
| --- | --- | --- |
| Tour:2701 | `~9 ESC ESC` / `home:request-knowledge-scan` | `2` / `melee` |
| Tour:3037 | `5` / `equipment-transaction:atomic-deposit` | `""` / `ownership:holder-await:calibration` |
| Tour:3052 | `~9 ESC ESC` / `home:request-knowledge-scan` | `""` / `ownership:holder-await:calibration` |
| Overweight:3723 | `~9 ESC ESC` / `home:request-knowledge-scan` | `3` / `shop:approach` |
| Town:1177 | `ESC` / `home-errand:filed:combat-weapon` | `ESC` / `home:store-context-exit` |
| Town:1916 | `woa` / `town:restore-combat-weapon` | `1` / `shop:approach` |
| Town:1922 | `~9 ESC` / `home-errand:request-knowledge:combat-weapon` | `""` / `ownership:holder-await:home-visit` |
| Town:1941 | `9` / `shop:approach` | `9` / `shop:approach` |
| Town:1947 | `da4 CR ESC` / `home:atomic-deposit` | `~9 ESC` / `home-errand:request-knowledge:combat-weapon` |
| Town:1957 | `de ESC` / `home:atomic-deposit` | `CR` / `shop:await-leave-confirmation` |
| Town:1958 | `~9 ESC` / `home-errand:request-knowledge:combat-weapon` | `CR` / `shop:await-leave-confirmation` |

## OFF stale-holder audit

The OFF deferral counts are tour 101, town 114, overweight 64. The hold
predicate admits only an open current claim, so a claim closed or expired on a
prior decision cannot freeze a producer. The replay audit found zero deferrals
whose linked visit was closed or whose operation had both released and observed
its effect. The `visit-closed-no-operation` release is also pinned in the S3a
class tests.

| Replay | Top holder claims by deferral count | Later outcome |
| --- | --- | --- |
| Tour | calibration #2571: 20; #2568: 16; #2569: 6; equipment-txn #2298: 5 | First two expire; latter two complete. |
| Town | store-router #893: 45; equipment-txn #843: 8; #834: 7 | Route remains open in capture; #843 releases, #834 completes. |
| Overweight | calibration #3402: 20; #3400: 16; #3401: 4 | First two expire; #3401 completes. |

These results rule out a closed or expired holder as the source of the OFF
deferrals. They do show live calibration claims held until expiry; ON exposes
four of those as `holder-silent` instead of hiding them.

## Tests

`s3-r4-test-counts.tsv` lists all 116 required modules and their individual
counts (3993 test cases, including one module with zero discovered tests).
All pass except `test_pure_decision_telemetry` (6 tests, 1 failure): its
first-town-visit lockstep has the same key/reason on both policies but one extra
`_aggregate_ranged_cache` entry at decision 8. Tracing shows fixed-quest
threat prediction recomputed one race on one policy while the other reused its
identity memo. The strict state equality assertion remains in place; this
cache-only failure reproduced with and without a fixed Python hash seed.
