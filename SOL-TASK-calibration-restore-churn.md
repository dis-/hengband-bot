# SOL-TASK: calibration deposit/restore churn and one-item-per-entry restore

Supervisor diagnosis, 2026-09-08, from the live run turns 1546801–1576680 (bot stopped mid-cycle;
game left running). Every claim is quoted from `jsonlog/bot-decisions.jsonl`.

The user's report: 「自宅からのアイテム回収でミスを連発している。正常ではない。」

## What the bot is actually doing

It is NOT resupplying. It is running **equipment calibration**, twice, back to back:

```
t=1571525  calibration phase -> deposit            (reason=shop:travel)
t=1572126  calibration phase -> strip              (reason=town-progress-invariant:defect:calibration:...)
t=1572359  calibration phase -> capture            (reason=calibration:request-naked-character)
t=1572359  calibration phase -> restore-supplies   (reason=calibration:redress)
t=1574209  calibration phase -> None               (cycle 1 COMPLETE)
t=1574625  calibration phase -> deposit            (reason=town-progress-invariant:boxed-breakout-...)
t=1575105  calibration phase -> strip
t=1575333  calibration phase -> capture
t=1575333  calibration phase -> restore-supplies   (cycle 2, still running when stopped)
```

## D1 — the restore withdraws ONE item per Home entry

```
t=1574029  calibration:atomic-restore-withdraw  key='5'
t=1574029  home:atomic-withdraw                 key='pM2\r\x1b'      <- ONE item
t=1574029  home:leave-after-one-operation       key='\x1b'           <- leaves Home
t=1574040  home:await-fresh-knowledge           key='9'
t=1574040  shop:travel:await-entry              key='5'
t=1574050  store:entry-await-observation        key=''
t=1574056  home:request-knowledge-scan          key='~9\x1b\x1b'     <- re-scans Home
t=1574056  shop:approach                        key='1'              <- re-approaches Home
t=1574056  home:store-context-exit              key='\x1b'
t=1574065  calibration:atomic-restore-withdraw  key='5'              <- next item, same dance
```

Counts over the window: **50 `home:leave-after-one-operation`, 25 `home:request-knowledge-scan`,
18 `home:atomic-withdraw`, 61 `home:atomic-deposit`.** Roughly forty game turns of travel, entry and
rescanning per single withdrawn stack.

This is the SAME inefficiency the user reported on 2026-09-06 (「自宅から1個ずつ回収している非効率」,
「毎回店と自宅を往復していて非効率極まりない」). The P1/P2/P3 repairs landed a Home BATCH for the
**procurement** path. The **calibration `restore-supplies`** path evidently never got it.

## D2 — calibration completes and immediately re-runs the identical cycle

Deposit keys, cycle 1 then cycle 2, and the restore between them:

```
cycle 1 deposits  (t=1572011-1572113): da10 da6 da15 da30 da5 da da da2 da da2 da47 da23
restore           (t=1573692-1574111): pa9 pc pc29 pc6 pd87 pd30 pm2 pp pM2 pO47 pO29
cycle 2 deposits  (t=1574955-1575089): da9 da da29 da6 da87 da30 da6 da da da2 da da2 da47 da29
restore 2         (t=1575973-       ): pa9 pc pc29 pc6 pd87 ...
```

The quantities match in both directions — 9, 29, 6, 87, 30, 2, 47, 29 go out and come back. **Net
change to the pack across a full cycle: nothing.** Between the two cycles the only real events were
two purchases (`shop:one-shot-buy` at t=1574560 and t=1574588) and a `restore:quaff-con`.

This is the `bot-alternating-owner-defect-class` signature: two owners alternate and neither
gold, depth, nor experience moves. Note also that the calibration phase is advanced by the bot's OWN
defect detector — `town-progress-invariant:defect:calibration:strip-installed=>...` and
`town-progress-invariant:boxed-breakout-...` — which fired **14 times** in this window. Progress
happens only when the defect detector kicks it.

Related standing notes: the calibration Home-visit budget was raised 54 -> 300 as a stopgap, so this
loop is bounded only by a 300-visit budget, and 300 visits is close to the 1500 town-stay cap.

## What is NOT established

The uppercase item selectors (`pM2`, `pO47`, `pO29`) DID work here — the game replied
"2個の…(k)", "47個の…(l)", "29個の…(m)". The uppercase-selector bell-loop landmine did NOT bite
in this window. Do not repair it on the strength of this evidence.

## The work

**D1 (repair):** batch the calibration `restore-supplies` withdrawals the way the procurement path
was batched — one Home entry should restore every pending stack it can, not one stack per entry.
Find the existing procurement batch (`_home_pending_batch` / `_home_procurement_batch_active` and
`home:process-next-batch-item`) and reuse that machinery rather than inventing a second batcher.
Do not weaken the one-operation-per-entry invariant where it exists for a reason — establish first
WHY `home:leave-after-one-operation` fires for the restore path, and say so, before changing it.

**D2 (diagnose, then STOP at a proposal):** why does calibration restart 416 turns after completing,
with the same pack? Determine from the artifacts whether (a) the completion is not being recorded,
(b) the trigger re-arms on something that the cycle itself changes, (c) the two purchases at
t=1574560/1574588 legitimately invalidate the calibration, or (d) something else. If the answer
implies a policy decision about when calibration should run, propose it and STOP —
spec-change-propose-not-implement. Only repair it in this round if it is an unambiguous bookkeeping
defect with a small fix.
