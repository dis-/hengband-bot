Step 1: live route and cause

Base d246d59b already includes 073fa4ba; no further merge needed.
Follow loop cli.py:4175/4291 calls _send_decision_key_with_prompt_chain.
Without a staged chain it calls _send_new_decision_key (cli.py:2718),
which uses _store_buy_continuations (2242, 2260, 2420).
For pk4\r\r\x1b its plan is pk; optional ITEM_SOURCE k bound to the
store chooser regex; QUANTITY 4\r; CONFIRM \r; STORE ESC.
submit_operation (cli.py:2136-2174) then invokes compile_observed_input.
On a Japanese STORE, observed_input.py:162-164 recompiles pk with _store_plan:
p; ITEM_SOURCE k bound to _BUY; then the existing optional chooser and gates.
_BUY only accepts the older Japanese purchase question. The recorded centered
chooser therefore fails the first, mandatory continuation before the repaired
optional continuation can be considered.

New production pin uses exactly sequence, turn, reason, key,
prompt_owner_handoff, with no observation. The live 213x68 screen is copied
verbatim; LF-normalized SHA256 is
7890e31e5cf0453542d89da02cb9063cc07237c4fc85e632a88370a68e4c47d8.
Recorded cap-08 is the initial STORE protocol sample; cap-06/07 are independent
quantity/price protocol samples, not later outcomes of the failed incident.
On d246d59b the pin fails: accepted ['p'], unowned item-source chooser.

Assertion audit before step 1 commit (verbatim):
No changed pre-existing assertions or forbidden test edits.

Step 1 commit: 3b0d6c02.

Step 2: observed_input.py:94 preserves the sender's recorded chooser binding
while splitting pk into p then a mandatory observed k. Quantity/price gates
remain bound to their recorded samples. No policy/checkpoint attributes added.
The English preservation branch retains its existing behavior.

The revert check restores only observed_input.py from d246d59b (identical
to 073fa4ba for this file), and the pin fails with accepted ['p'] and
unowned item-source. Restoring the fix passes with accepted
['p', 'k', '4\r', '\r', '\x1b'] and completed. The first capture attempt
encountered a subprocess cp932 decoding error; repeating with explicit UTF-8
produced storewhich2-revert.txt. No test assertions were changed.

Verification, one module per process:

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_storewhich2_recorded | 1 | OK |
| tests.test_storewhich_recorded | 2 | OK |
| tests.test_shop_one_shot | 53 | OK, 1 existing skip |
| tests.test_classA_observed_input | 30 | OK |
| tests.test_input_executor | 73 | OK |
| tests.test_cli | 234 | OK |
| tests.test_live11 | 2 | OK |
| tests.test_test_fakery_lint | 13 | OK |

408 tests run, 1 existing skip. stuck OFF: 4 rows, unchanged hash
c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5.
stuck S3.3: no divergence, trajectory_defect null.
withdraw OFF: 34 rows, unchanged hash
a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9.
withdraw S3.3: expected first divergence at sequence 3, ESC,
equipment-transaction:catalogue-leave-for-scan; trajectory_defect null.
EXPECTED_FIRST untouched. Live game and bot untouched; live success is not claimed.

Assertion audit before step 2 commit (verbatim):
No changed pre-existing assertions or forbidden test edits.
