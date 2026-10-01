# live27 step 1

Base: main 2bb7fa41, branch decl-r3b. Full recorded public-entry replay
reproduces decisions 0..104, including the departure-unsatisfiable stop.
The new pin fails before the fix: expected town:identify-staff-stockout-mining,
actual town:blocked:departure-unsatisfiable; carried charges 18, mode prepare,
planned runs None, Home knowledge current, attempted stores {7: 692214}.

- Carried charges: policy.py:12778 `_total_identify_staff_charges` sums
  `_stack_charges` for carried Identify staffs. policy_supply.py:301-318
  enforces the threshold, policy_constants.py:354/362 defines depth 10 and
  20 charges. Home stock does not satisfy readiness.
- Home reserve: recorded 101 queues it; 102 sends `5pl1\r\x1b`; 103 reports
  `2本の 鑑定の杖 (2x 9回分)(h)を取った。` and procurement current 18,
  target 20, missing 2. The extraction command printed these recorded fields.
- Shops/Home owners finish before the terminal, policy_town.py:5722-5740;
  after cross-town and supplier counterfactual return no action the terminal
  fires. Recorded 85..96 are Morivant full-identification travel, rather than
  proof of acquiring additional carried Identify-staff charges.
- The existing Identify stockout condition policy_town.py:5254-5264 excludes
  prepare/mine/scavenge. This character is already in prepare, so the one-run
  Identify plan is never installed. Its predicate policy.py:14530-14569 also
  requires a Magic attempt, absent after the town change (only Home remains).
- Recall stockout uses policy.py:14488-14527 to install one planned run,
  clear supplier/route attempts and retry after mining. Identify already has
  the equivalent helper policy.py:14571-14588, but the entry excludes this
  incident. policy_town.py:5274-5286 clears completed run state and rearms
  procurement. policy_town.py:3987-3998 protects the Identify time-pass from
  premature termination at the gold target while the shortfall persists.

Decision: 「10F以降に潜る場合は鑑定の杖の合計チャージ20回を必須とする。
調達が不可能な場合は採掘で時間経過させること。」
The prompt's decoded text is quoted here; the supplied prompt explicitly says
the total counts carried charges. No UI classification or modal code changes
are needed, so R2 requires no new live-screen fixture.

Assertion audit: No changed pre-existing assertions or forbidden test edits.
Changed pre-existing assertions: none.

Calibration wall: extraction freezes the currently available calibration;
historical byte identity is not assumed. Replay identity through all 105
decisions is the fidelity evidence. No recorded board after the first changed
decision will be interpreted as a consequence of the mining key.

# live27 step 2

Fix: policy_town.py:5739-5748 invokes the existing Identify one-run stockout
helper after the current town claims, cross-town route and departure supplier
counterfactual are exhausted. It requires the existing depth/charge shortfall
and does not reinstall an outstanding Identify mining plan. Generic prepare
mode can now become the one-run time-pass. No threshold or readiness predicate
changes, no new persistent attributes, no EXPECTED_FIRST edits.

Recorded procurement evidence printed from the frozen source:
`VISITS {'0': 3, '7': 12, '4': 5}`. The audited constants print
`0 '!' -> STORE_GENERAL`, `4 '%' -> STORE_ALCHEMIST`,
`5 '&' -> STORE_MAGIC`, `6 "'" -> STORE_BLACK`, `7 '(' -> STORE_HOME`.
This process visited General, Home and Alchemist; it did not establish that
Magic/Black were physically empty. After the cross-town trip only Home remains
in the attempted-store map. The selected boundary is exhaustion of executable
owners, not an added interpretation of shop stockout.
The last Home page before 102 prints store 7, index 11, letter `l`,
`鑑定の杖 (2x 9回分)`, count 2, charges/pval 9. Thus `pl1` targeted
that recorded staff address; the subsequent carried stack has 18 charges.
An earlier withdrawal was observed at 45: `鑑定の杖 (9回分)(g)を取った。`.
Morivant bought *Identify* scrolls (observed at 54), not the missing carried
Identify-staff charges.

Fail-before / pass-after:

```
before: SHORTFALL 18 mode prepare planned None home_current True stores {7: 692214}
before: ('5', 'town:blocked:departure-unsatisfiable')
after: FIRST DIVERGENCE 104 live '5' town:blocked:departure-unsatisfiable replay '5' town:identify-staff-stockout-mining
after: SHORTFALL 18 mode prepare planned 1 home_current True stores {}
```

The new pin passes at the public town-surface entry, with all 104 preceding
decisions matching the recorded key/reason. Checkpoint restoration also selects
the same one-run plan. Named counterfactual charge-only boards show 19 fails
and 20 satisfies readiness. A separately constructed completed-run state on
the recorded stop board exercises the existing return transition: mode/plan
and supplier attempts clear, while the 18-charge departure gate remains false.
This is a transition pin, not a claim about unrecorded mining effects.
The single revert in scripts/live27_revert_check.py removes only the production
hunk: the recorded pin fails once with the original stop, and a finally block
restores the hunk. Output is in reports/live27-revert.txt.

Verification (each module its own process; exactly the requested name matches
and the three explicitly named modules):

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_identify_staff_live27_recorded | 1 | pass |
| tests.test_crossarea_fundraising | 12 | pass |
| tests.test_departure_unsatisfiable_weight_recorded | 7 | pass |
| tests.test_policy_fundraising | 50 | pass |
| tests.test_quest_carry_departure_recorded | 4 | pass |
| tests.test_recall_stockout_set_end_recorded | 5 | pass |
| tests.test_recall_stockout_surplus_pins | 8 | pass |
| tests.test_town_progress_invariant | 22 | pass |
| tests.test_ownership_s2a_classification | 16 | pass |
| tests.test_test_fakery_lint | 13 | pass |

Total: 138 tests. Existing module-name matches contain no identify_staff module
before this change. No full-suite runner or generic matching-module sweep ran.

Authorized stuck/withdraw measurements, each case/mode in a separate process:

| Fixture | OFF hash | S3.3 first divergence |
| --- | --- | --- |
| stuck | c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | none |
| withdraw | a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | index/sequence 3; early-divergence |

Withdraw S3.3: OFF `~9\x1b`, `home:request-knowledge-scan`; ON `\x1b`,
`equipment-transaction:catalogue-leave-for-scan`. EXPECTED_FIRST remains
`[20, 20, '\x1b\u0060n%.', 'shop:travel']`. Loading only the baseline
2bb7fa41 `_town_special_key` method in memory and repeating the authorized
withdraw S3.3 measurement yields the identical index-3 early-divergence.
This existing mismatch is pending Claude; no expectation was changed.
The script exits 0 for this measured defect, so it is not reported as a
successful S3.3 trajectory check.

DO-NOT-RUN / pending Claude: scripts/test_parallel_runner.py,
scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py,
scripts/mutation_battery.py; tests.test_cli, tests.test_policy_town,
tests.test_policy_shop, tests.test_absorbing_states; long tour/town/overweight
recorded replays, town producer purity parts, full-fixture runs of
scripts/first_divergence_s3_3.py and generic matching-module sweeps. Only the
specifically authorized stuck/withdraw exception was run for that script.
No Claude review or message was requested or sent.

Assertion audit before step-2 commit (verbatim):
`No changed pre-existing assertions or forbidden test edits.`
Changed pre-existing assertions: none. The new pin's JSON hash compares
normalized LF bytes, so Windows checkout newline conversion does not break it;
the extractor writes new JSON using LF. Calibration JSON content is unchanged.

Commits: step 1 `16ebba7e`; step 2 is the commit containing this report's
step-2 section, production fix and final pins.
