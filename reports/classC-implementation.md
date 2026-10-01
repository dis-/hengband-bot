# Class C implementation and verification

Scope: branch `classC` in `C:\hengband\bot-client-live21`, base `be0befed`.
Step 1 audit commit: `6d7d401d`. Step 2 implementation commit: `3be2ac5a`. The final result record
also names the audit and implementation SHAs.

## One rule

A departure shortfall is not unsatisfiable until its decided state-changing
remedy has been offered and exhausted. Exhaustion of one shop or the equipment
owner does not exhaust independent owners. The ordinary and recall departure
requirements remain unchanged; existing producer bounds and named failure
verdicts remain. No new attributes, thresholds, UI handling, or requirement
exemptions were added.

## Fixes

| File:line | Change | Why it satisfies the rule |
|---|---|---|
| `src/hengbot/policy_shop.py:1292` (second old writer removed at baseline :1341) | Remove the two shop-router `departure-unsatisfiable` writes and the return before terminal settlement | The shop plan can finish without preventing recovery, supplier retry, identification settlement or stockout mining. The final departure evaluator retains the generic typed stop. |
| `src/hengbot/policy_town.py:3328` | Scope equipment exhaustion to equipment-work/transaction candidates | Recall, food, light, teleport, cure, Identify charges and safe weight deposits can still select a reachable supplier. The exhaustion flag still suppresses optional launcher enchanting. |
| `src/hengbot/policy_town.py:5174,5744,5775` | Share the existing restock-wait predicate between early selection and both late verdict boundaries | Evaluating the exhausted plan can install restock after the early check already ran. Offer that exact wait on this board, before either an equipment blocker or the generic stop. Keep failed departure leaves false. |

The additional audit finding is the blanket equipment-exhaustion return at
baseline `policy_town.py:3326-3336`: it discarded every independent candidate.
A second late finding is that `_terminal_equipment_blocker` calls
`_next_required_store_type`, which can install `_town_restock_wait_until` after
the early restock check. Before the final fix, the constructed teleport board
printed `town:blocked:departure-unsatisfiable` with a newly populated wait;
the light board printed `town:blocked:equipment-calibration-required` with a
newly populated wait. The corresponding final pins now emit `R300\r`.

## Audit summary: conjunct → decision → wiring

The exhaustive 33-entry, predicate/producer/decision table and exact memory
quotes are in [classC-audit.md](classC-audit.md). This table groups equivalent
mechanisms; aliases remain distinct entries in that audit.

| Conjunct(s) | Decided remedy or stop | Final wiring |
|---|---|---|
| recall_departure_ready | D1/D2/D5/D12: carried stock, Home first, local restock/mining; no ordinary recall-stock waiver | Independent supplier survives equipment retirement; existing local one-run owner retained |
| identify_staff_ready | D1/D2/D3/D9: 20 carried charges from 10F; unavailable → one mining run and retry | Supplier survives retirement; exhausted shop cannot preempt live27's mining owner |
| food_ready | D1/D2/D7/D9: carried food, Home first, fundraising first-run exception only as already decided | Supplier preserved; newly installed General/Magic restock is offered before stop |
| light_ready | D1/D2/D8: usable light even for mining | Supplier preserved; newly installed General restock precedes stop, including independent equipment refusal |
| teleport_ready, cure_critical_ready | D1/D2/D9/D17: required carried stock, replenishment, preserved shortage | Suppliers preserved; same-board Alchemist/Temple restock precedes stop |
| quest_carry_ready | D6: quest-entry stock condition; ordinary dives proceed through stockout | Existing normal-departure constant true and quest gate unchanged |
| inventory_weight_ready | D4: deposit safe excess first; visible stop on genuine Home failure | Existing live36 deposit, retention and Home rearm preserved; equipment retirement no longer erases the deposit supplier |
| free_pack_slots_ready, organization_complete | D5/D10/D18: identified excess deposit before purchase/ID/rewards; identify before disposal | Existing deposit/organization/overflow pipeline remains; shop exhaustion is no longer a generic departure verdict |
| hp_full, mp_full, temporary_status_clear | Existing recovery while fed; no new policy for unrepairable cases | Shop exhaustion cannot preempt recovery; typed stop remains without an executable producer |
| equipment_departure_ready, combat_weapon_ready, calibration_loadout_restored, calibration_phase_complete, calibration_restore_complete | D7/D11/D16/D19 and authoritative depth table: optimize/restore, required body armour, complete or last confirmed legal loadout only | Existing equipment and calibration gates/transactions unchanged; independent supplies can proceed while equipment is exhausted |
| teleport_items_safe | D11/D18: safe equipment/disposal; no approved extra fallback for irrecoverable cases | Existing safe-weapon/disposal producer retained; no permission to depart with unsafe items |
| home_candidate_resolved, home_catalog_ready, home_pending_item_clear, home_pending_batch_clear, home_batch_review_clear, home_atomic_withdraw_clear, digger_withdrawal_resolved | D2/D10/D15/D16: scan, exact withdrawal/review/confirmation, named failure | Existing Home producers and pending-operation priority retained; no fabricated Home completion |
| identification_need_clear, departure_identification_need_clear | D2/D10/D15: identify, source procurement or decided defer/retry | Existing terminal settlement is reached after shop exhaustion; no new identification policy |
| departure_home_pending_item_clear, departure_home_pending_batch_clear, departure_home_batch_review_clear, departure_home_atomic_withdraw_clear | D2/D10/D15/D16: same Home producers without availability exemption | Existing stricter recall leaves unchanged |
| recall_landing_not_guardian_blocked | D14: alternate legal landing, deeper allowed; visibly stop without alternate | Existing independent destination gate unchanged |

D13 Black Market reserve remains the actual outstanding required-supply cost;
no optional-purchase or reserve code changed. Body armour selection and the
depth requirements also remain unchanged; this round repairs remedy dispatch.

## Production pins and causality walls

New module: `tests.test_classC_departure_remedies` (5 tests).

- :39: seven failed supply/weight leaves each select the actual supplier and
  route key before a stop despite equipment retirement; live policy and a
  restored checkpoint both run. The optional-work exhaustion flag is retained.
- :118: the production exhausted-shop router hands the board to the existing
  Identify stockout owner: `5`, `town:identify-staff-stockout-mining`, one run.
- :132: the same production router preserves `town:recover` for HP/status.
- :146: an already installed stockout-plan boundary does not waive the gate
  or reinstall a plan; the existing typed stop remains.
- :158: food, light, teleport and cure shortages get the newly installed
  `R300\r` remedy on the same board, still failing their original leaf.

The input is the existing live36 recorded attachment; variations are explicitly
constructed exported pack/player/map facts and declared retirement/no-effect
evidence. The mapless board has no exported store entrance and does not match
the static town dimensions. These are not later historical boards or outcomes
of new keys. Existing live27 and live36 recorded pins remain the public-path
acceptance gates. No screen classification or modal code changed (R2).

Printed final supplier evidence (from the new pin module):

```text
CLASS C SUPPLIER identify_staff_ready 5 '\x1b`n&.' shop:travel
CLASS C SUPPLIER recall_departure_ready 3 '\x1b`n$.' shop:travel
CLASS C SUPPLIER food_ready 5 '\x1b`n&.' shop:travel
CLASS C SUPPLIER teleport_ready 4 '\x1b`n%.' shop:travel
CLASS C SUPPLIER cure_critical_ready 3 '\x1b`n$.' shop:travel
CLASS C SUPPLIER light_ready 0 '5' shop:travel:await-entry
CLASS C SUPPLIER inventory_weight_ready 7 '\x1b`n(.' shop:travel
CLASS C SAME BOARD food_ready 'R300\r' town:wait-restock:general
CLASS C SAME BOARD light_ready 'R300\r' town:wait-restock:general
CLASS C SAME BOARD teleport_ready 'R300\r' town:wait-restock:alchemist
CLASS C SAME BOARD cure_critical_ready 'R300\r' town:wait-restock:temple
```

Identifier meanings were printed from `src/hengbot/model.py`:
`STORE_GENERAL = 0`, `STORE_TEMPLE = 3`, `STORE_ALCHEMIST = 4`,
`STORE_MAGIC = 5`, `STORE_HOME = 7`. Route literals above are the printed
production output, not a guessed mapping of a travel symbol.

Single revert checks are in `classC-single-revert.txt`:

- Shop fix reverted: stockout pin fails with the premature generic verdict.
- Shop fix reverted: recovery pin fails with the same premature verdict.
- Supplier-core fix reverted: all seven leaf subcases fail with `(None, True)`.
- Late-restock checks reverted alone: all four shortage subcases fail; three
  issue the generic stop, light issues the equipment-calibration stop.
- Every reverted source file was restored in `finally`; final verification
  runs on the restored complete implementation.

## Verification

Final requested verification: **11 modules, 272 cases, 268 passed, 4 pre-existing skips, zero failures**.

| Module | Tests | Skipped | Result |
|---|---:|---:|---|
| `tests.test_classC_departure_remedies` | 5 | 0 | PASS |
| `tests.test_live36_weight` | 7 | 0 | PASS |
| `tests.test_identify_staff_live27_recorded` | 1 | 0 | PASS |
| `tests.test_departure_unsatisfiable_weight_recorded` | 7 | 0 | PASS |
| `tests.test_town_progress_invariant` | 22 | 0 | PASS |
| `tests.test_policy_home` | 184 | 4 | PASS |
| `tests.test_quest_carry_departure_recorded` | 4 | 0 | PASS |
| `tests.test_recall_stockout_set_end_recorded` | 5 | 0 | PASS |
| `tests.test_recall_stockout_surplus_pins` | 8 | 0 | PASS |
| `tests.test_ownership_s2a_classification` | 16 | 0 | PASS |
| `tests.test_test_fakery_lint` | 13 | 0 | PASS |

Final results and module counts are in `classC-verification.json`; each module
has its own `classC-tests.*.txt` log. Only the explicit requested module list
ran, one module per process, with `PYTHONPATH=src;tests;scripts` and the full
Python313 executable (not WindowsApps).

Modules matching the requested departure/stockout names, enumerated before
execution, are exactly:

- `tests.test_departure_unsatisfiable_weight_recorded`
- `tests.test_quest_carry_departure_recorded`
- `tests.test_recall_stockout_set_end_recorded`
- `tests.test_recall_stockout_surplus_pins`

Also: the new module, `tests.test_live36_weight`,
`tests.test_identify_staff_live27_recorded`, `tests.test_town_progress_invariant`,
`tests.test_policy_home`, `tests.test_ownership_s2a_classification`, and
`tests.test_test_fakery_lint`. Existing Home tests include four pre-existing
lost-substrate skips in `HomeWithdrawTargetUnobservedRecordedPins`; no skip or
assertion was changed.

The permitted fixture exception is recorded in
`classC-fixture-verification.json` (plus per-case full JSON/logs):

| Fixture | OFF SHA256 | S3.3 first divergence | Defect |
|---|---|---|---|
| stuck | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | none | none |
| withdraw | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | `(3,3,ESC,equipment-transaction:catalogue-leave-for-scan)` | none |

Both OFF and S3.3 were run separately. `EXPECTED_FIRST` was never edited.
The fix applies before generic departure, after earlier survival/operation
owners; it cannot authorize departure because every readiness leaf remains.

## Remaining decisions and pending Claude work

No approved extra remedy was found for unrecoverable HP, MP, temporary status,
or a teleport-unsafe item with no executable safe-equipment/disposal producer.
The existing producers run, and exhaustion retains the visible typed stop.
Deciding an additional remedy for these cases is user policy work, not an
implementation relaxation. No Class C implementation blocker remains;
the explicit final verification completed successfully.

DO-NOT-RUN work remains pending for Claude under the imported hard rules:
`tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`,
`tests.test_absorbing_states`; long tour/town/overweight recorded replays;
town-producer purity parts; full-fixture runs/sweeps of
`scripts/first_divergence_s3_3.py`; `scripts/test_parallel_runner.py`,
`scripts/test_timing_runner.py`, `scripts/hunk_guard.py`,
`scripts/verify_scope.py`, `scripts/mutation_battery.py`, and full-suite gates.
The four lost Home pins need fresh capture as already recorded by their skip.
No game, bot, executable, jsonlog, other worktree or pre-existing untracked
file was changed. No live run or post-divergence success is claimed.

## Test and assertion manifest

`tests/test_classC_departure_remedies.py`: added only; production remedy order,
seven independent supplier leaves, same-board restock, recovery, hard-stop
retention and restored checkpoints. No existing test changed/renamed/deleted;
no pre-existing assertion changed. Assertion audit output is stored verbatim
in `classC-assertion-audit.txt` and the final result record.

assertion_audit (verbatim, base `be0befed`):

```text
No changed pre-existing assertions or forbidden test edits.
```
