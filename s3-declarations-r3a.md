# S3.3 producer declarations, round 3a

This round is record-only. The emitted key and legacy claim reader remain authoritative. Offers bind only when both the final key and claim owner match the producer's offer. No declaration is synthesized at claim exit.

| Family | Producer sites with declarations | Declared for every admitted return? |
| --- | --- | --- |
| home-visit | `policy_home.py` direct page deposit success and rejected leave; existing composed operation and staged tail | **Partial**. Atomic withdraw/deposit and open-page no-step exits still lack a producer declaration on every return. Other Home page leaves remain unclassified. |
| home-errand | `policy_shop.py` active, identity-bound request leaving the Home page; `policy_home.py` unaddressed withdrawal retry/leave; existing composed withdrawal | **Partial**. Filing is a Boolean helper with no final key; its other callers and remaining withdrawal exits still need declarations bound to their emitted key or None. |
| home-scan | `policy.py` outside knowledge requests, open-page request/incomplete-page leave/completion-page leave, and held observation wait | **Partial**. Deferred no-step paths have not been exhausted. The request/posted observation identity also needs an end-to-end audit. |
| shop-buy / shop-sell | `policy_shop.py` direct `_shop` page result names purchase, sale, leave, page command, or no-step; one-shot compose and released tail have distinct acting declarations | **Partial**. Other direct sell, one-shot no-step and store-page no-step paths need an emitted-key audit. |
| store-router | Existing generic and store travel offers; `policy_shop.py` entry observation wait and no-neighbor step-off release; `policy.py` short entrance and store-route fallback directions | **Partial**. Other entry/leave and router no-step paths, including route refusal and page handoff, still need explicit declarations. |

The target of zero undeclared admitted paths was **not reached**. The remaining paths need producer-specific work identities and a check of which key ultimately leaves the decision. The one-shot composition offer is deliberately `acting` with no posting transition on its wait key; the released operation tail is the first key that can become a posted mutation.

Remaining paths requiring work:

- `policy_home.py` `_atomic_home_withdraw_key`, `_atomic_home_deposit_key`, and `_open_home_deposit_key`: their early `None` results can be a rejected probe before another producer emits a key, or the final no-step. A declaration needs the caller's final disposition and the pending operation identity; offering release from every helper `None` would misstate a continuing Home visit.
- `policy_home.py` `_file_home_errand` and its `policy_equipment.py` caller: filing returns a Boolean, then the caller chooses the final key. The request needs an explicit next executor at the key-producing caller. The latter file is outside this round's assigned producer files.
- `policy.py` deferred Home scans: `_defer_town_errand` returns `None` before holder arbitration can emit a different key. An offer on the deferred probe would attach to the wrong producer; the scan's final no-step needs a named release or held request identity at its return site.
- `policy_shop.py` `_atomic_shop_transaction_key` uncomposable and plan-advance exits: the page selector can emit `None` or a wait while mutating plan state. Each branch needs an explicit cause or next planned stop, including cases where the caller selects another key.
- `policy_shop.py` `_shopping_approach_key` and `policy_town.py` `_town_travel_key`: entry failure, route refusal and unresolved-step exits can yield an empty key or `None`, then the router may fall back. The route producer must state whether it retains the destination, releases it, or waits for a posted entry before the final key is bound.

Verification: `tests.test_execution_declaration` passed (20 tests), `tests.test_policy_helpers` passed (23 tests), `tests.test_policy_home.HomeOneOperationPerEntryTest` passed (91 tests), and `tests.test_test_fakery_lint` passed (13 tests). Five source-removal checks each made its corresponding new family pin fail. A focused OFF/S3.3 ON shop-page key/reason check passed. No prohibited gate, full suite, or full replay was run. The OFF/ON result is limited to that class case; it is not a replay identity proof.

Family commits: `1f01cb1a`, `97f12a3c` home-scan; `2bf641c9`, `977aecfc` store-router; `1d1d4826` home-visit; `5f5c3764`, `e5754015` shop-buy/shop-sell; `37d9a935`, `8a7924c0` home-errand.

{"topic":"declarations-r3a","implementer":"gpt-6-sol","status":"partial","record_only":true,"zero_undeclared":false,"families":{"home-visit":"partial","home-errand":"partial","home-scan":"partial","shop-buy/shop-sell":"partial","store-router":"partial"},"full_fixtures_run":false,"commits":["1f01cb1a","2bf641c9","1d1d4826","5f5c3764","37d9a935","97f12a3c","e5754015","8a7924c0","977aecfc"]}
