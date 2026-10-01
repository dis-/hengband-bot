# Class A3

## Step 1: cause and owner/text audit (base 0d6349a7)

`src/hengbot/observed_input.py:141,145` binds all identify targets to
`IDENTIFY_ITEM_PROMPT` (normal Japanese/English). `src/hengbot/input_executor.py:1171-1180`
accepts full Japanese/English target text only for identify:full-equipped.
Thus carried identify:full stops at the captured full chooser after r,i.
Classifier lines 259-260 already recognize both forms.

Source text pairs (policy_identification.py:59-64):
- r: READ_KEY: ("どの巻物を読みますか? ", "Read which scroll? "),
- u: USE_STAFF_KEY: ("どの杖を使いますか? ", "Use which staff? "),
- z: ZAP_ROD_KEY: ("どのロッドを振りますか? ", "Zap which rod? "),
Normal target: ('どのアイテムを鑑定しますか? ', 'Identify which item? ')
Full target: ('どのアイテムを*鑑定*しますか? ', '*Identify* which item?')

| Owner | Source | Target accepted before | Required target |
| --- | --- | --- | --- |
| identify:normal | r/u/z pair for actual command | normal | normal |
| identify:normal-equipped | r/u/z pair | normal | normal |
| identify:device | r/u/z pair | normal | normal |
| loot:identify-floor-item | r/u/z pair | normal | normal |
| quest:sweep:identify | r/u/z pair | normal | normal |
| home-disposal:identify-before-sale | r/u/z pair | normal | normal |
| identify:full | r (full scroll) | normal, incorrectly | full |
| identify:full-equipped | r (full scroll) | normal OR full, incorrectly | full |

Source gates depend on command, not owner: scroll/staff/rod use SOURCE_PROMPT.
Other scroll/staff/rod owners use the same source pair and no identify target;
identify:complete and identify:batch-complete are bookkeeping without a chooser.
Producers: policy_town.py:1946,2022,2102,2141; policy_equipment.py:2528;
policy.py:12266. Existing explicit chains use normal target tuples, including
full-equipped policy_equipment.py:2545, so executor normalization must cover them.

No new policy/checkpoint attributes. No EXPECTED_FIRST changes.

## Assertion audit

No changed pre-existing assertions or forbidden test edits.

## Step 2: fix and evidence

input_executor.py:1175 normalizes each identify owner's target gate to exactly
its command's normal or full Japanese/English suffix, covering explicit legacy
chains and the common production sender. Source gates retain SOURCE_PROMPT.
The normal aliases quest:sweep:identify and home-disposal:identify-before-sale
are included (policy_quest.py:1001 and policy_home.py:3421).

All other r/u/z owners are source-only unless they have an explicit separately
bound target continuation; they accept only the command's source pair above.
This includes scroll escape/light/detection/recall/enchantment, staff/rod utility,
and item use: full identify text cannot be mistaken for a source chooser.
Library service town:morivant-full-identify:library uses a store service, not
an r/u/z item chooser; travel/stockout/queued-withdraw/buy-identify/complete
reasons do not open identify item choosers.

Fixture full-target.json is a verbatim copy of the 2026-10-01 19:41 screen.
SHA256 normalized CRLF to LF:
a1273db71ce717c083fac3f65c20cedcee0358ea31d2f794639ef3acf95a480a.
before.json is the last turn-1516229 board in the incident state JSONL archive.
The source UI and command wait are declared protocol controls; the production
sender receives recorded key ris + ESC tail and owner identify:full, seq 1126.
Before: accepted r,i and stuck at full target; after: r,i,s with no blind ESC.
Stop after the first new target answer; no post-divergence effect asserted.

The three new pins fail twice with the production file reverted and pass with
the fix. An initial revert run could not capture output due to cp932 decoding;
repeated with explicit UTF-8 output for the saved single revert result.
The old stage2f pin used a normal chooser for full identification. Replaced
only that screen with recorded full-target.json; all assertions unchanged.

User requirement: each owner accepts exactly its command's source/target texts,
both languages. Normal/full cross-owner controls stop; full recorded carried
selection posts s. No live game or bot operation performed.

Normal targets additionally retain the continuation's original feature/page
and language binding. Full targets replace the legacy normal-text binding;
equipped identity/page checks remain enforced by the existing executor.

## Verification

Each module ran in its own Python 3.13 process with PYTHONPATH=src;tests;scripts.

| Module | Tests | Final result |
| --- | ---: | --- |
| tests.test_classA3_full_identify | 3 | OK |
| tests.test_classA_observed_input | 29 | OK |
| tests.test_input_executor | 73 | OK |
| tests.test_live13_full_equipped_identify | 1 | OK |
| tests.test_live15_identify_source | 2 | OK |
| tests.test_live17_identify_observation | 2 | OK |
| tests.test_live18_identify_result | 2 | OK |
| tests.test_live30_identify_normal | 9 | OK |
| tests.test_test_fakery_lint | 13 | OK |

134 tests passed. Initial input-executor failures exposed the obsolete full
chooser control and an English/Japanese binding restriction; both resolved
without changing assertions. Evidence is in validation/classA3-*.

| Replay | OFF rows / hash | S3.3 first divergence | Defect |
| --- | --- | --- | --- |
| stuck | 4 / c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | none | none |
| withdraw | 34 / a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | 3: ESC / equipment-transaction:catalogue-leave-for-scan | none |

Both S3.3 rows equal EXPECTED_FIRST. No declaration gaps/mismatches; gate-final
counts stuck OFF/ON 0/0, withdraw OFF/ON 20/0. Historical missing detector
declarations remain stuck 1 and withdraw 2 under OFF, as before.

## Pending for Claude (DO-NOT-RUN)

The prompt explicitly preserves the inherited DO-NOT-RUN block, with only
stuck/withdraw exceptions. Therefore tests.test_cli remains pending despite
appearing in the requested verification list. Also pending: tests.test_policy_town,
tests.test_policy_shop, tests.test_absorbing_states; long tour/town/overweight
recorded replays; town producer purity portions; full-fixture first_divergence
runs; all-matching-module sweeps; scripts/test_parallel_runner.py,
scripts/test_timing_runner.py, scripts/hunk_guard.py, scripts/verify_scope.py,
scripts/mutation_battery.py, full-suite and gate scripts.

## Commits

Step 1: 09760b67 (cause and source/target audit).
Step 2: see the fix commit containing this report and CLASSA3-EVENT.json.
