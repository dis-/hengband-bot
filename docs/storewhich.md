# Store chooser incident, 2026-10-01

Step 1: base 2f7f5ba0 already strips leading whitespace for the English
and Japanese store/Home chooser at input_executor.py:262-266. The recorded
213-column screen is classified ITEM_SOURCE, not rejected by that regex.
The rejection is input_executor.py:1316: _store_buy_continuations
(cli.py:2420-2436) owns quantity/confirmation/store only, after posting pk.
The observed chooser therefore has no owner to answer k.

Recognizer inventory at the base:
- input_executor.py:232-234 quantity: suffix search, column reported as zero.
- :215,229-230 Home character dump filename: startswith at column zero;
  core/asking-player.cpp renders the filename at row zero without store offset.
- :244-266 Home equipment/deposit and store/Home chooser: suffixes or lstrip,
  column reported as zero. Japanese chooser regex is anchored after lstrip.
- :300-329 Home knowledge viewer: centered width-derived offset, and an
  explicit 80-column fallback; these are display geometry, not column-zero assumptions.
- :351-373 store/Home footer: centered width-derived offset but Python
  character slicing; replace with existing East-Asian display-cell slicing.
- :748-789 stock/page binding: already uses centered origin and cell slicing.

Recorded row zero (verbatim, leading spaces retained):

```text
                                                                  (商品:a-Z, ESCで中断) どれ?
```

Recorded slot k (verbatim, padding trimmed):

```text
k) ! 4服の スピードの薬                                       0.2         352
```

No policy/replay decisions or EXPECTED_FIRST values are changed.

Step 2: normalize chooser features and quantity features while reporting their
actual display-cell origin. Slice store/footer lines by display cells, using
live18's existing helper. Add an optional, bilingual, pattern-bound store chooser
continuation to one-shot buys: if the original atomic p+slot reaches quantity,
it is skipped; if the chooser is observed, answer only this purchase's slot.
Quantity, confirmation and exit remain observed continuations. No new persistent
attributes, thresholds, or checkpoint fields.

The incident chooser pin calls the production CLI sender. The later quantity
and confirmation screens are existing independent cap-06/07 protocol samples,
not purported observations after the incident's k/4 purchase. No game or live
bot was touched; no purchase effect is claimed.

Assertion audit before both commits:
`No changed pre-existing assertions or forbidden test edits.`
Single revert of both production files to 2f7f5ba0 failed with the original
unowned item-source stop (exit 1); restored code passed.

Validation (one module per process):
- tests.test_storewhich_recorded: 2 passed.
- tests.test_shop_one_shot: 53, 1 skipped.
- tests.test_classA_observed_input: 30 passed.
- tests.test_input_executor: 73 passed.
- tests.test_cli: 234 passed.
- tests.test_live18_identify_result: 2 passed.
- tests.test_live35_store_page: 3 passed.
- tests.test_policy_shop: 279, 1 skipped.
- tests.test_test_fakery_lint: 13 passed.

Only stuck/withdraw subsets of first_divergence_s3_3.py were executed, each mode
in a separate process. Stuck OFF: 4 rows, digest
c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5;
S3.3: no divergence, trajectory_defect null. Withdraw OFF: 34 rows, digest
a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9;
S3.3: first divergence at index/sequence 3, exactly EXPECTED_FIRST:
OFF key ~9\x1b / home:request-knowledge-scan; ON key \x1b /
equipment-transaction:catalogue-leave-for-scan. trajectory_defect null.
Replay stops at first divergence; later boards are not evidence of ON effects.
