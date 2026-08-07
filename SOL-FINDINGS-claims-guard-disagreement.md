# SOL-FINDINGS: claims guard disagreement inside the installing decision

## Scope and acceptance

**MEASURED.** I restored only turn 2942063 from that record's own checkpoint and snapshot, wrapped the
restored policy at runtime from `scratchpad/probe_claims_guard_disagreement.py`, and called public
`choose_key` once. The replay reproduced the live installing result exactly: key `5`, reason
`town:blocked:no-safe-recall-destination`. It is accepted under the task's rejection rule. No live
process, bot lifecycle state, or hold was touched. No committed source was edited.

## Call-by-call trace

| Order | Call and caller | Measured result | Relevant state / effect |
| --- | --- | --- | --- |
| 1 | `_find_home_deposit`, from `_calibration_town_key` at `policy.py:8750` | slot `a`, `鑑定の杖 (2x 14回分)`, count 2 | Phase `deposit`; pending Home/disposal slots both `None`; no policy attribute changed. |
| 2 | `_town_claims_active`, from `_decide` at `policy.py:4476` | `True`, categories `['deposit']` | Deposit NeedSpec produced. Home=7 was not blocked, `approach_fails[7]=0 < 54`, but `need_attempts['deposit']=8 >= budget 3`. The exemption at `policy.py:13717-13721` was true because nested `_find_home_deposit` (`:13719`) returned the same staff. Deposit is non-departure-blocking, but departure readiness was false, so the claim survived `:13724-13730`. |
| 3 | `_shopping_approach_step`, from `_decide` at `policy.py:4483` | `None` | `_is_oscillating()` was true and `_shop_approach_stuck_count` entered as 11. The stuck branch at `policy.py:17571-17576` set `_shopping_stuck=False -> True`, `_town_store_attempted[7]=2942063`, `approach_fails[7]=0 -> 1`, and the stuck count to 0. This is the within-decision state change. |
| 4 | `_activate_safe_recall_fallback`, from `_town_special_key` at `policy.py:19080` | `None` | Full `policy.__dict__` before/after diff: **no mutated attributes**. |
| 5 | `_town_claims_active`, from `_town_special_key` at `policy.py:19083` | `False`, categories `[]` | Need candidates rebuilt after order 3 contained no deposit because Home was now in `_town_store_attempted`. The deposit spec failed `spec.produces` at `policy.py:13713-13715`; `_find_home_deposit` was not called, so the exemption was never evaluated. The ledger remained below the calibration ceiling (`approach_fails[7]=1 < 54`), with budget/attempt `3/8` and Home not blocked. |

Every `_find_home_deposit` call returned the same slot-a staff and changed no policy attribute. There
was no differing finder result. The state changed between calls at `_decide ->
_shopping_approach_step` (`policy.py:4483`, mutation at `:17572-17575`): adding Home to
`_town_store_attempted` prevented the later NeedSpec producer from reaching `_find_home_deposit`.

## Exact `_town_special_key` control flow

**MEASURED.** The line trace entered at `policy.py:18709`. The early full-identify, not-in-town,
cycle-pending, existing-block, restock-wait, fundraising, rumor, loadout-fallback, recall-shortage,
ready-recall, and non-ready recall branches all fell through. At the destination assertion, the three
guards at `policy.py:19075-19079` were true: target was Angband, Angband recall was unlocked, and
Angband recall safety was false. Fallback at `:19080` returned `None`. The claims guard at `:19083`
returned `False`, so `:19084` did not return `None`; assignment executed at `:19085`, followed by
`_town_blocked_key` at `:19086`.

## Why the guard did not return `None`

**MEASURED answer.** This was a within-decision disagreement, not an unguarded assignment path. The
first claims check saw a real calibration deposit and returned `True`. Its attempted Home approach
then hit the generic oscillation-stuck branch, which immediately recorded Home in
`_town_store_attempted` and incremented `approach_fails[7]` to 1. When `_town_special_key` reached the
guard later in the same decision, that attempted-store mark suppressed deposit in
`_town_need_candidates`; the deposit NeedSpec did not produce, the exemption's "currently
discoverable" check was never called, and `_town_claims_active` returned `False`. Therefore the guard
did not return `None`, and line 19085 installed the latch.

## What the capture's `town_claims: true` proves

**MEASURED.** `latch_onset_capture.py:157-163` restores a new disposable clone from the saved
predecision checkpoint and evaluates `_town_claims_active` while building the record, after the live
decision completed. Thus the field is evaluated at **record-build time on predecision state**, not at
assignment time on the already-mutated live policy. Its `True` proves the checkpoint independently has
a deposit claim; it does not prove the live policy still had that claim at `policy.py:19085`.

## Repair options

The trace makes two repair directions obvious; neither is implemented here.

1. **Defect repair:** do not let the generic oscillation-stuck branch add calibration Home to
   `_town_store_attempted` on the first approach failure. Keep it claim-producing until the existing
   calibration Home ceiling (54) actually terminates it. This aligns the attempted-store latch with
   the authoritative calibration bound.
2. **Behaviour/spec change:** make the final destination guard preserve a discoverable calibration
   deposit despite an attempted-store mark. This broadens the guard's ownership semantics and must
   still specify how an actually unreachable Home terminates.

## Not established

**NOT ESTABLISHED.** This trace does not establish which repair is preferable, whether the generic
oscillation detector's count of 11 is itself correct, or how often the transition occurs outside
calibration. It establishes only the accepted installing decision and the state transition that made
its final guard false.
