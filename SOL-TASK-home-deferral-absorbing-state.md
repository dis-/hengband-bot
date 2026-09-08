# SOL-TASK: the Home-deferral absorbing state behind `town:blocked:home-withdraw-failed-stock-present`

Supervisor diagnosis, 2026-09-08. Every claim below is quoted from live artifacts in
`jsonlog/bot-decisions.jsonl` (the run that ended 2026-09-06 19:34) — no mechanism is asserted
without one.

## What the bot actually did

The decision log ENDS on a visible stop:

```
t=1463659 home:route-claim-unfulfilled                   key='\x1b'
t=1463668 shop:travel                                    key='\x1b`n#.'
t=1463668 store:entry-await-observation                  key=''
t=1463985 town-progress-invariant:continue-observed-shop key='\x1b'
t=1463995 town:blocked:home-withdraw-failed-stock-present key='5'
```

`home:route-claim-unfulfilled` occurs 9 times across turns 1417434 → 1463659 — the bot repeatedly
approaches Home, enters, observes a complete 43-item scan, and leaves having done nothing.

## The decisive record (turn 1463995)

```json
"home_gate": {
  "result": "blocked",
  "branch": "wrapper-withdraw-failed-stock-present",
  "item": {"tval": 18, "sval": 1, "letter": "q", "price": 3, "category": "ammo"},
  "candidate": null,
  "candidate_absence_census": {"class_matches": 2, "excluded_as_deferred": 2,
                               "zero_count": 0, "torch_no_fuel": 0},
  "deferred_matches": [
    {"identity": ["クロスボウの矢 (1d5) (+0,+0) (19/shot 21/turn)", 18, 1],
     "site": "town-item-processing-missing-pending"},
    {"identity": ["クロスボウの矢 (1d5) (+0,+0) (19/shot 21/turn)", 18, 1],
     "site": "town-item-processing-missing-pending"}
  ],
  "inputs": {"knowledge_current": true, "knowledge_invalidated": false, "attempted": true,
             "blocked_store": true, "fails_at_limit": false, "approach_fails": 0,
             "unsatisfied_passes": 6, "visit_limit": 3}
}
```

**Every class match is excluded as deferred: `class_matches == excluded_as_deferred == 2`.**

## The chain, with file:line

1. `policy_town.py:1010` defers a Home item when the withdrawal is posted but the item is not
   observed in inventory afterwards:
   `self._defer_home_item(self._home_pending_item, "town-item-processing-missing-pending")`.
   Its own comment scopes the deferral to **"the current town visit"**.
2. `_deferred_home_items` is cleared in exactly two places:
   - `policy_observation.py:584`, inside `if snapshot.in_town:` **and**
     `if snapshot.floor_key != self._floor_key:` — i.e. ONLY on arriving in town from elsewhere.
   - `policy.py:2469`, a `difference_update(carried_signatures - home_signatures)` that only drops
     signatures now carried and no longer at Home. The bolts are still at Home, so it never fires.
3. The B2 Home-first gate deliberately uses the **unfiltered** class census (that was the correct
   fix for the earlier defect where the deferral filter hid single-item stock), so it counts the
   deferred bolts as stock present and publishes
   `town:blocked:home-withdraw-failed-stock-present`.
4. The visible stop prevents departure, so the floor never changes, so the deferral never clears,
   so (3) repeats forever.

**This is an absorbing state with no bot-reachable exit** — the `bot-absorbing-survival-state`
defect class. Corroboration that the deferral is stale rather than fresh: the last 60 MB of the
decision log contains **zero** `home:withdraw-failed-deferred` records while `deferred_matches`
still carries two, across 96 `home:leave-after-one-operation` events.

## What is NOT the defect

The visible stop itself is the user's LOCKED decision, quoted verbatim:
「引き出し失敗の場合は自宅に物品がない場合は購入して良いが、自宅に物品がある場合は報告して停止。」
Do NOT weaken it. Do NOT re-introduce a deferral filter into the census — that reverts a correct
earlier repair. The stop is right; what is wrong is that its premise ("the withdrawal failed") is a
stale fact from an earlier Home visit that was never retested.

## The repair

Give the deferral a **bot-reachable retry boundary**, so the stop is published only after a FRESH
withdrawal attempt has failed.

- When the Home gate is about to publish `home-withdraw-failed-stock-present` and
  `class_matches > 0 and class_matches == excluded_as_deferred` — i.e. the ONLY thing standing
  between the bot and the stock is a deferral — clear the deferrals for that class and retry the
  withdrawal once.
- Bound it so it cannot loop: at most ONE retry per signature per town stay, tracked in state that
  clears on the SAME boundary as `_deferred_home_items` (never on Home re-entry — a per-entry reset
  would recreate the alternate-forever loop the deferral was written to prevent).
- If the retry also fails, publish the visible stop as today, and record in the stop's telemetry
  that a fresh attempt was made and failed. The stop then reports a real failure instead of a stale
  one.
- The user's rule is untouched: stock at Home still means report-and-stop. Only the freshness of
  the "withdrawal failed" premise changes.

## Second, smaller question to answer in the same round

The same record shows `"unsatisfied_passes": 6` against `"visit_limit": 3`. Six unsatisfied Home
passes against a limit of three means a bound exists and did not retire the claim. Determine from
the artifacts whether that is (a) two different bounds being compared, (b) a bound that counts
something other than passes, or (c) a real failure of the town-liveness invariant
(`town-liveness-invariant`: in town, movement is not progress, and an unsatisfiable claim must
self-retire). Report which; only repair it in this round if it is (c) and the fix is small —
otherwise write it up as a separate finding.
