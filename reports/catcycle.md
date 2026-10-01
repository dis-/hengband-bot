# catcycle investigation (base 0d6349a7)

Step 1: the registered equipment-txn catalogue holder is supposed to send the
outside scan: `policy.py:6805-6842` already returns HOME_KNOWLEDGE_MACRO outside
and declares `equipment:acquire-home-catalog` / `home.catalogue.acquire`.
The declaration alone does not dispatch a producer. `policy.py:8825-8827` calls
it only inside Home with cross-area or S3.3 sequencing enabled; the generic
holder dispatcher at `policy.py:6392-6393` belongs to enforced town admission.
The earlier public choose-key branch at `policy.py:7435-7477` instead approaches
Home on an outside entrance with stale knowledge and a nearly full warrior pack.
It replaces the continuation with `home.approach-for-equipment-catalog`, so the
partial page leaves again. The ordinary outside scan at `policy.py:8319-8354`
also excludes every store entrance; it cannot rescue this board.

Recorded decisions 1063-1125 are frozen with original source line indices and
source hashes in tests/fixtures/catcycle/provenance.json. Rows 1064,1066,...1122
are 30 catalogue ESCs; rows 1065,1067,...1123 are 30 re-entry 5s. The supplied
63-row window includes the initial travel and rows 1124/1125; it is not 63 full
enter/leave pairs. All 32 Home boards in the cycle window show page_top=0,
stock_num=63, and 52 visible items. Thus it revisits the same partial first page,
not successive pages. Any partial page enters the same incomplete-page branch.

Why 1124: row 1123's equipment-txn claim 720 is retired. Retirement is applied
at `policy.py:4674-4675`; `_claim_errand_hold` (`policy.py:5620-5626`) accepts
only open holders. After the recorded 5 opens Home, the retired holder cannot
win the catalogue branch. The routed, invalidated page then reaches the ordinary
open-Home scan (`policy.py:9037-9059`) under a new home-scan claim 721. Row 1125
records that claim completing home-knowledge-current, followed by route-unfulfilled.

Required behavior: "the registered catalogue work, after leaving for the complete
list, posts the knowledge scan as its own next step (declared by the same owner),
adopts the catalogue, and only then re-enters Home". Ruling #9's withdraw row
must remain `(3,3,ESC,equipment-transaction:catalogue-leave-for-scan)`; no changes
to EXPECTED_FIRST are authorized.

No pre-existing assertions changed. No runtime/game/other-worktree writes.
