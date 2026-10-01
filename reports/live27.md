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
