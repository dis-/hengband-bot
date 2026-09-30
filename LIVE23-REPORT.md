# Live23: recorded Home catalogue / digger alternation

Baseline: `ca369103`; branch `decl-r3b`. Source capture is read-only.
The fixture provenance records source hashes and exact state line indices.

## Step 1 — recorded evidence before implementation

(a) Entry succeeds. Decision 1972 sends `5` at (45,123), turn 670848;
state line 2263 (zero based) is a Home page with 24 items, stock_num 24,
page_size 52. `policy_shop.py:4851-4873` intentionally activates the entrance
with `5`. `policy.py:7274-7326` takes the early catalogue acquisition path
because the nearly full pack has invalidated Home knowledge. Its execution
expects `home-catalog-available`, but `policy.py:4251-4267` completes the
store-entry claim merely because the page opened. Thus it enters repeatedly,
rather than failing to enter.

(b) `policy.py:8761-8775` calls `_queue_standing_home_digger` before adopting
the complete observed catalogue. `policy_equipment.py:506-534` requests two
diggers regardless of departure purpose, binds one, and sends ESC. The
recorded fundraising mode is None throughout 1962–1975: this is ordinary
exploration, so this withdrawal is unwanted under the user's mining-only rule.
The invalid catalogue remains invalid, restarting the entry path.

(c) Home deposit claim 1656 completes at 1972 (`home-deposit-observed`).
Equipment claim 1657 then registers catalogue acquisition before home-visit
claim 1658 at 1973. The latter gets the decision because the Home branch
does not continue catalogue acquisition and entry completion drops 1657
before a producer's claimed effect (`home-catalog-available`) was observed.
Claims 1659/1660 repeat this at 1974/1975.

(d) `_record_decision_claim`, `policy.py:4354-4373`, completes the prior claim
before `_s33_shadow_verdict` sees it. At 1973, 1657 has closed; the shadow
has no standing holder. `policy.py:4932-4939` fills an absent shadow holder
with the newly declared actor (1658, home-visit). Likewise the next cycle
uses equipment-txn. ON calls the same premature completion before entry
gates (`policy.py:2703-2711`), so registration order cannot protect the work.
The holder must remain the registered catalogue work until its evidence is
observed or it releases by name; entry is a step, not that work's completion.

Existing untracked `.live8b-revert.py` was present before this task and is untouched.

## Verification restrictions

The inherited DO NOT RUN block forbids `tests.test_absorbing_states` and
all town producer purity parts; these remain pending for Claude. The live23
instruction explicitly permits the stuck/withdraw OFF+S3.3 fixtures. No live
bot, game, other worktree, or runtime/jsonlog file is changed.

## Step 2 — root fix

`policy.py:3899` binds the goal to the producer's named `home-catalog-available`
effect as a knowledge Observe. Entry remains a physical step; the work ends
only when the catalogue is adopted. An existing restored store-entry
declaration retains its identity, completion evidence and original expiry
budget (`policy.py:4268`), rather than being retargeted mid-operation.

`policy.py:6723`–`6749` derive ownership from the standing registered work,
without introducing persisted policy attributes. The real Home-page branch
dispatches that work before other Home producers (`policy.py:8762`). A
complete recorded page is adopted and the claim closes `home-knowledge-current`;
an incomplete page leaves under the same owner to request the complete list
outside. Typed wrong-store release is `catalogue-wrong-store`.

`_defer_town_errand` and `_town_producer_entry` (`policy.py:5829`, `5911`)
protect an already registered physical Home sequence with cross-area OR S3.3
ON. Both catalogue entry paths ask before mutation (`policy.py:7387`, `10914`),
and `policy_shop.py:4785` asks before route composition. This covers either
registration order, including later mining withdrawal behind catalogue work.

`policy_equipment.py:506` restricts the digger withdrawal to fundraising's
mining departure modes when either switch is ON, and asks the same ownership
predicate. Both switches OFF retain the legacy key behavior.

The shadow now sees the registered equipment-txn before the row actor is
declared: the recorded home-visit ESC yields
`would_stop=ownership:gate-missing:home-visit`, `holder_family=equipment-txn`,
with the original holder's claim id. The unchanged actor fallback is used only
when there was no standing holder after a genuine observed completion.

User decisions followed:

- 2026-09-27 「目的の重複＝登録済み優先」: the production entry attachment adopts
  the catalogue under equipment-txn before any later withdrawal; the reverse
  Home-operation-first case skips equipment before its producer runs.
- 2026-09-18 「通常探索では採掘具を自宅に預ける（優先度最低）」,
  採掘目的の出発時のみ携行: recorded ordinary return (mode None) does not queue
  the digger. Supplemental mining-purpose cases still queue it after admission.

## Pins and validation

The public production attachment primes from incident state line 2262,
adopts the earlier recorded 23-item Home catalogue, and applies the real
post-deposit invalidation. Player skill fields come from the last recorded
skill reply before the incident (line 2232). The first key remains live's `5`;
the next recorded Home page is therefore action-consistent. At that page the
new result is ESC / `equipment-transaction:home-catalog-acquired`, with 24
catalogue items, no pending digger, and completion of the original claim id.
The old result was ESC / `home:queue-digging-tool-withdraw`, without adoption.
The replay stops at this decision. Tests do not consume later historical
boards as consequences of a new decision.

Before fix: the three initial pins failed (five assertion failures across
cases); checkpoint testing was changed to the real checkpoint codec because
plain pickle included an unpicklable derived town-need registry. The single
source-revert check restores all three changed production files to ca369103:
all six new tests run, 11 assertion failures, no errors. The source is restored
in a finally block. After fix: six tests pass, including restored old entry
declarations and an independently attached recorded partial Home page.

Each requested test module ran in its own normal Python 3.13 process with
`PYTHONPATH=src;tests;scripts`:

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_live23_home_cycle | 6 | pass |
| tests.test_town_progress_invariant | 22 | pass |
| tests.test_s33_shadow_recorded | 6 | pass |
| tests.test_policy_home | 184 | pass, 4 existing skips |
| tests.test_equipment_transaction_planner | 15 | pass |
| tests.test_equipment_transaction_session | 15 | pass |
| tests.test_live8 | 11 | pass |
| tests.test_live22_bounty | 8 | pass |
| tests.test_ownership_claims | 24 | pass |
| tests.test_ownership_s2a_classification | 16 | pass |
| tests.test_test_fakery_lint | 13 | pass |

Total: 320 tests run, 316 passed, 4 existing skips. Classification initially
flagged three new undecorated producer exits; adding the equipment-txn producer
declaration fixed it without changing assertions. The new partial-page pin
also caught retargeting of a legacy restored declaration; preserving its
existing goal fixed it, and the final six pins plus recorded shadow module
were rerun successfully. No pre-existing assertions or EXPECTED_FIRST changed.

Authorized fixture measurements, one fixture per process:

| Fixture | OFF rows / SHA256 | S3.3 ON first difference |
| --- | --- | --- |
| stuck | 4 / c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | none |
| withdraw | 34 / a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | row/index/sequence 3: `~9 ESC` / home:request-knowledge-scan → ESC / equipment-transaction:catalogue-leave-for-scan |

Withdraw's recorded page at that decision contains 52 of 131 Home items.
The standing catalogue claim now continues through the partial page, rather
than completing at entry and handing the UI to a later scan. The measuring
script labels this `early-divergence` because the frozen EXPECTED_FIRST is
still row 20. That expectation is deliberately untouched; this changed
production behavior is disclosed for Claude's review. ON stops measurement
at row 3; no subsequent recorded board is replayed as its effect. The separate
partial-page pin verifies same-id continuation and restored dispatch without
inventing an outside board. Raw measurement JSON is in `validation/live23/`.

Pending for Claude, explicitly prohibited by the inherited DO NOT RUN block:
`tests.test_absorbing_states` and one town producer purity part (producer was
touched; part 1 is suggested). No long tour/town/overweight runs or other gates
were executed.

Assertion audit (verbatim, base ca369103):

```text
No changed pre-existing assertions or forbidden test edits.
```

`git diff --check` also passed. The evidence commit is `f424d3b4`; the fix and
final reporting commits are recorded below after their creation.
