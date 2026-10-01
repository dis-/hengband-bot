# batchfixB

Base: a4e51bf9. Work is confined to bot-client-c2. Runtime jsonlog and other
worktrees are read-only. Every module runs in its own process.

## Step 1 observations

* guardian: six failures; first key/reason divergence index 2, captured
  `\x1b\x60n%. / shop:travel`, current `\x1b\x60n(. /
  equipment-transaction:travel-home`. Later bounce observations are not evidence
  of effects of that changed key. The dual-wield selector is under investigation.
* calibration live25: four subcases at extra weight 322 restore 1546 rather than
  1551. Before 19a6fd1f the module passes; after ammunition fitting the projected
  overweight debt also loses one ammunition unit. Cause: policy_home.py:63
  retention consults the unchanged full projected pack for each debt reduction.
* Home stage1: H1/H10 reject `ti` at executor admission; supplementary rejects
  `do`. Cause: input_executor.py:992-998 does not recognize the existing
  `policy:` owner envelope. Identical three failures reproduced on d7429e7b,
  so the premise that these passed on that revision is false. The causing
  admission guard is 28ee9a9a (git blame).
* Home alternation: first decision 591 selects k rather than b. Identical
  failure reproduced on d7429e7b. policy_home.py's complete-overload preference
  (6c8941cf, predating these merges) promotes an identification supply above
  ordinary surplus despite the declared category priority.
* Home stock-present: first changed board index 5 selects Home's ordinary
  withdrawal rather than Theoden's equipment withdrawal. The combat arithmetic
  pin also depends on the capture-time optimizer selection and is under audit.
* S3.3 r14: OFF trajectory hash differs (8a1bd0b05855aa06378b01f93a10a839bbec0352f4a9dcb9552312e73307df19).
  EXPECTED_FIRST and OFF_SHA remain untouched; the earlier equipment divergence
  must be resolved before the ownership gate can be measured.

Historical sources are read through git archive into a temporary directory
inside this worktree. No checkout of another worktree is performed.

No assertion edits or new UI classification have been made in Step 1.

## Step 2 implementation

No new policy/checkpoint attributes, tunable thresholds or UI forms are added.

1. Calibration's projected pack is reduced immediately after each supply debt
   is discharged to Home. Subsequent ammunition retention sees the remaining
   debt, so five torches clear the extra unit of weight without also dropping
   an ammunition unit. The boundary arithmetic is 1379 + 322 - 5*30 = 1551.
   19a6fd1f^ passes the original module, 19a6fd1f fails all four extra=322
   subcases; the fix passes all six tests, including pickle-restored checkpoints.
2. Executor admission interprets the existing `policy:` envelope, retaining
   the complete owner in receipts. The store/map command distinction stays in
   force. All 16 Home stage1 tests complete with the original eight expected
   failures, and all 73 executor tests pass. The source-context change causing
   the three failures is 28ee9a9a, already present in d7429e7b.
3. The Home identification handoff keeps its blocking identification supplies
   until an actionable carried target is identified. The original candidate
   guard already excludes the target itself. Extending that protection to its
   unreserved identification supplies selects b at decision 591, then yields
   to identification at weight 1655; consuming the five-weight identification
   scroll reaches 1650. Both original alternation pins pass. The original
   `clears` preference is retained; no broad disposal reordering was introduced.
   Its k-over-b failure also exists on d7429e7b, rather than being introduced
   by one of the listed October merges (the preference traces to 6c8941cf).
4. Guardian and overweight replays use immutable, signature-bound historical
   optimizer results, following the same declared-collaborator-wall mechanism
   already adopted for town/live27/classC2 in 460b49e8. The approved clause is
   "dual-wield half-max-melee selection, ruling #9" (batchfix common prompt).
   It would be incorrect to run captured post-command boards as the responses
   to today's different gear transactions. Their own ownership, Home ledger,
   loot and guardian assertions are unchanged. Unknown optimizer inputs fail
   closed. Fixtures record source_revision d7429e7b and use normalized-LF
   content hashes per R9. Historical reconstruction uses the old selector and
   old melee bonus distribution, never a fabricated success predicate.
5. The stock-present combat pin is a combat/optimizer subject, so it uses
   today's production optimizer rather than freezing it. Six exact assertions
   change as the direct result of 7410a5cb. The recorded crossbow's +10/+8 is
   excluded from melee: shield/empty-hand hit probabilities become 0.72/0.74,
   damage per hit becomes 27.378331183077933/29.499501110425385. Current
   Avabia/shield DPS is 154.7946732249078 versus Theoden/empty 109.14815410857393;
   the approved half-max-melee-before-survival rule keeps the worn kit. At the
   first changed decision, 5, the Home supply withdrawal replaces the old
   Theoden withdrawal. The test consumes no historical response beyond that
   changed command. All six stock-present tests pass. Before/after/quoted
   clause for every changed assertion is recorded in event.jsonl.

## First-divergence attribution for every failing pin

| Module / failing pin | First divergence | Causing commit / seam | Resolution |
| --- | --- | --- | --- |
| guardian / g1 fallback | index 2: shop:travel -> equipment-transaction:travel-home | 7410a5cb; equipment_optimizer.py `_stable_operational_best`, warrior_equipment_evaluator.py `_distributed_bonus` | captured gear input; original guardian assertion |
| guardian / g1 valve | same prefix index 2 | same | original Forest(7) valve assertion |
| guardian / g2 bounce count | same prefix index 2 | same | original bounce count assertion |
| guardian / live replay identity | same prefix index 2 | same | original full identity assertion |
| guardian / r3 visible stop | same prefix index 2 | same | original visible terminal assertion |
| guardian / S2b.2 OFF bars | same prefix index 2 | same | original empty bar assertion |
| overweight / every Home effect resets passes | index 2: shop:travel -> equipment-transaction:takeoff (`tb`) | 7410a5cb, same optimizer seams | captured gear input; original ledger counts |
| overweight / stop board proceeds to deposit | same prefix index 2 | same | original Home deposit assertion |
| overweight / production loot boundary | same prefix index 2 | same | captured gear input; live loot observer remains production |
| overweight / pre-stop replay identity | same prefix index 2 | same | original keys/reasons unchanged |
| overweight / S2b.2 hunts | same prefix index 2 | same | original seven bar records |
| Home stage1 / H1 | operation 1 `ti` rejected at admission | 28ee9a9a, input_executor.py `submit`, predates the merge range | code interprets policy owner envelope |
| Home stage1 / H10 | same operation 1 | same | same code fix; original visit counts |
| Home stage1 / supplementary deposit | operation 0 `do` rejected | same | same code fix; original keys/ownership assertions |
| Home alternation / identification then weight | captured decision 591: k rather than b | already fails d7429e7b; preference 6c8941cf; policy_home.py `_weight_deposit_candidates` | protect actionable identification's blocking supplies |
| stock-present / shield and weapon terms | index 5: Theoden gear withdrawal -> ordinary Home supply withdrawal | 7410a5cb | six precise ruling-based expectation changes |
| r14 / overweight Home tail at 3715 | OFF stream already differs at index 2 | 7410a5cb, shared overweight replay | captured gear input; EXPECTED_FIRST unchanged |
| live25 / extra=322, OFF, direct | full restore macro: one ammunition unit omitted, 1546 vs 1551 | 19a6fd1f; policy_home.py `_plan_calibration_supply_restore` | update projected pack after each reduction |
| live25 / extra=322, OFF, checkpoint | same restore plan | same | same code fix; restored checkpoint pin |
| live25 / extra=322, S33, direct | same restore plan | same | same code fix |
| live25 / extra=322, S33, checkpoint | same restore plan | same | same code fix; restored checkpoint pin |

The guardian historical baseline passes all seven pins; 7410a5cb fails the
short G1 prefix at index 2. Overweight's raw production prefix likewise changes
at index 2; historical-prefix logs show the before/after keys without consuming
a subsequent board. Historical reconstruction with today's non-equipment code
passes all 12 overweight tests. These are legitimate optimizer consequences,
not a reason to undo the approved production optimizer.

Single in-memory seam reverts fail the original calibration boundary (four
subcases), alternation and H1 tests. Revert scripts reject test import errors
as evidence. The full code is never rewritten for these checks.

Printed current source references: equipment_optimizer.py:1127 (half-melee
filter); warrior_equipment_evaluator.py:253 (bonus distribution);
input_executor.py:996 (producer-envelope interpretation; base guard :992-998);
policy_home.py:26/:63 (calibration planning/reservation), :68 (projected pack
reduction), :1218/:1229 (actionable identification supply protection).
These references apply to the per-pin attribution table above.

All invocation logs are stored here. PowerShell stderr capture wraps ordinary
unittest progress in NativeCommandError text; the actual unittest summaries
and test outcomes, rather than that wrapper, determine the reported result.

## Final verification

All explicitly requested modules were run separately, plus the directly
touched executor module and required test-fakery lint. 172 tests ran; the eight
pre-existing stage1 expected failures remain expected failures. No ordinary
failure or error remains in this verification.

| Module | Tests | Result |
| --- | ---: | --- |
| guardian_recall_pingpong_recorded | 7 | OK |
| overweight_home_unreachable_recorded | 12 | OK |
| equipment_in_home_stage1 | 16 | OK, 8 existing expected failures |
| home_withdraw_failed_stock_present_recorded | 6 | OK |
| home_withdraw_deposit_alternation_recorded | 2 | OK |
| declarations_r14 | 2 | OK |
| calibration_live25 | 6 | OK, all four restored/direct boundary subcases |
| classC2_departure_recorded | 9 | OK |
| classC_departure_remedies | 5 | OK |
| live36_weight | 4 | OK |
| town_approach_retired_recorded | 8 | OK |
| identify_staff_live27_recorded | 1 | OK |
| catcycle | 4 | OK |
| crash_position_key_recorded | 1 | OK |
| input_executor | 73 | OK |
| test_test_fakery_lint | 13 | OK |

`python scripts/first_divergence_s3_3.py overweight s33` ran in one process:
3782 OFF rows, unchanged OFF hash
`8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b`;
first ON difference (3715, historical sequence 3714), OFF `rjp` /
`identify:device`, ON ESC / `home:leave-after-one-operation`;
`trajectory_defect=null`, ON `gate_final_count=0`, no town declaration gaps
or mismatches. OFF's existing 24 gate-final observations remain baseline
telemetry; they are not new ON stops. No result past the first ON difference
is presented as an effect of the ON command.

Every one of the six assertion changes is enumerated with before/after/quoted
clause in event.jsonl; assertion-audit.txt contains the audit output verbatim.
There are no weakened/removed assertions, new forbidden defect expectations,
deleted pins or edits to EXPECTED_FIRST/OFF_SHA. `git diff --check` passes.

Step 1 commit: c9411c46. Step 2 commit: the commit containing this final report,
the code fixes, replay inputs and event. No live/game files or other worktrees
were modified; the excluded runners and full suite were not run.
