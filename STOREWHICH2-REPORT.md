Step 1: live route and cause

Base d246d59b already includes 073fa4ba; no further merge needed.
Follow loop cli.py:4175/4291 calls _send_decision_key_with_prompt_chain.
Without a staged chain it calls _send_new_decision_key (cli.py:2719),
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

Assertion audit before step 1 commit: PASS: no assertion weakening or suspicious expected values
