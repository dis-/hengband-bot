# Live22 recorded investigation (step 1)

Baseline: 2fe5a02e, branch decl-r3b. No game/bot activity.

The recorded state tail contains 143 boards, turns 647164?647858; the initial 3731?3735 decisions have no corresponding boards in the state archive. The checked-in fixture copies five original state lines and four decision lines for 5123?5126, turns 647164?647181. This is the same recurring cycle, not fabricated initial boards. Stop a replay at its first changed key; later recorded boards are independent attachments only.

* The bounty producer wants the Hunter Office (building type 13), at (25,71), to redeem slot r, ??????????? {???}. It wants nothing from store 4. `policy.py:16038-16097` routes to the office and composes its existing cashout tail; `policy_town.py:1712-1737` unconditionally exits any store whenever a bounty remains, before purchasing. Decision 5125 therefore leaves store 4 immediately.
* `policy_town.py:718-827` measures movement against `_shopping_approach_goal`, even though the bounty producer declares Reach(25,71). The stale supplier goal is store 4 at (37,91). Movement 7 from (36,90) toward the office moves away from that supplier and is rejected. `policy_town.py:953-1032` composes a supplier counterfactual, then `policy_town.py:1347-1351` replaces the key with 3. The helper retains the bounty label although its key now enters the supplier. The recorded detector claim explicitly targets store (37,91).
* `town_arbiter.py:133,154` splits bounty approach into store-router and leave/cashout into quest-request. `_town_order_step4_key` has no internal family gate (`policy_town.py:1720-1737`); `_town_producer_entry` bypasses gate recording while S3.3 is OFF (`policy.py:5886-5888`). Suspended store-router claim 2538 persists while quest-request exits. Decision 5125 shadow: ownership:gate-missing:quest-request.
* Each detector/quest/router change resets or resumes another claim instead of charging one bounty operation. The legacy repeated-transition detector (`policy_helpers.py:103-151`) requires game-turn span smaller than decision span; this cycle advances turns (647164,647173,647181), so it never satisfies that predicate. Only the external 1500-decision detector terminates the session.

Evidence: incident-20261001-0625-town-loop-bounty-approach.{state,decisions,ownership-claims}.jsonl.gz, plus 20261001-062440-loop-detected/meta.json (read-only originals).

Verification instruction conflict pending: inherited DO NOT RUN prohibits tests.test_absorbing_states and all town producer purity parts; live22 explicitly requires them but names only stuck/withdraw as exceptions. Those prohibited checks require clarification.
