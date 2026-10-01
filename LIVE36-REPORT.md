# live36 — departure weight recovery

Base `d1bf7c28`; branch `live36`; only this worktree changed.

## Step 1

Frozen evidence: `tests/fixtures/live36-weight.json:1` (verbatim board,
decision records 7514–7520, Home page and serialized shelf memories; source
hashes included). Extraction: `scripts/extract_live36_weight.py:15`.

* Stop 7520: carried pack plus equipment 1780 tenth-pounds, limit 1750;
  STR index 29. Only `inventory_weight_ready` failed. Weight calculation:
  `src/hengbot/policy_home.py:1100`; `policy_helpers.py` sums pack and worn.
* Actual retention, reproduced using the recorded optimization depth 20
  and the sanctioned pending Q2 profile: a oil 5/5, b speed 2/2, c cure 10/10,
  d healing 4/4, e teleport 15/15, f recall 10/10, g light 6/6, h light wand
  1/1 (MANA food), l iron shot 99/99. No surplus in these stacks.
  i Identify staff 1/0, j Identify staff 2/0, k Identify staff 2/0 are outside
  the quantity retention table (`policy_home.py:815`). They are not all safe
  to remove: i's 17 charges are needed; j or k can be removed independently
  while preserving Identify and MANA food. Existing charge-aware selector
  with its count-cap bypass chooses k (2 × weight 50), leaving 27 Identify
  charges, above the unchanged 20-charge requirement. The recorded pack has
  no unidentified loot or unknown items.
* `policy_home.py:1187` rejects required-category items with reservation 0;
  `:1237` applies that filter to all three staff stacks. Thus the overweight
  producer has no candidate. The typed verdict follows that failure, rather
  than preempting an available deposit. Independently, cumulative
  `need_attempts[weight-overload]=5` exceeds its budget 1 and would suppress
  the repaired need at `policy_town.py:3059`. Home had zero unsatisfied passes,
  no blocked store and no approach failures; this is not a failed deposit.
* Last observed Home page: stock 57, capacity 240 (183 free slots), followed
  by the successful withdrawal at 7510. No subsequent deposit could have
  filled it. Home room is not the blocker.

The seam attachment primes the real outside board and supplies captured
depth, shelf/attempt memories, Q2 abandoned force requirements and ledger.
It does not reconstruct the entire prior process. No recorded board after
a changed key is interpreted as its result (R4). No UI classification or
modal continuation changes are proposed, so R2 needs no new screen.

Initial pin run: 3 tests, 1 passed, 2 failed (no deposit; no weight claim).
No existing assertions changed; EXPECTED_FIRST untouched.
