# Step 1.5d, part 2: continue past a rejected purchase and finish the Identify swap

## Revision 2

Design-only revision, 2026-10-10; applies all seven required review changes:

1. Guard the whole ordinary-store relief dispatch after effect accounting,
   including subsequent knowledge/WAIT paths (F3(b), two-decision S11 pin).
2. Remove post-refusal buy composition after a mutating `_shop`; enumerate
   in-shop recovery reasons and retain only the atomic settlement veto (F2(c)).
3. Align churn exclusions with the floor-transition sale-signature reset and
   document process-local lifetime, not autorecover persistence (F2(a)).
4. Require pack absence and no pending Home take for completed disposal;
   seed the real launcher producer and preserve pending Home disposal (F2(b)).
5. Publish the final stop through `_town_blocked_key` under the existing
   town-plan prefix; preserve the ownership classification digest (Reasons).
6. Add ledger normalization/private-seam tests and explicitly unchanged
   Home-side controls (Existing tests).
7. Declare the constructed 014739 reconciliation boundary and 184438 Home
   state; make the three-plus-one control primary (Verified capture pins).

Also adopt the limited-signature exclusion recommendation (F2(a)). Apply the
owner's 10-10 decision, 「空の杖は自由に売って良い」: empty Identify staves are
surplus, may be taken for sale/destruction without a fuller supplier offer or
a one-staff limit, and are never rejected by the relief cap guard (F3(c),
184438 and three-plus-one pins). F2 remains first, F3 follows its HEAD;
implementation task pins and test lists are in Implementation order.

Design only, 2026-10-10. Implementation base: **a8833b0b**, branch
`step1.5d-identify-staff`, main `777f9f55` plus F1/F4. This document covers F2/R1
and F3/R3 from section 4 of `STEP1.5d-IDENTIFY-STAFF-ANALYSIS.md`, under
`PLAN-town-stability-20261009.md` 手順1.5. References below are relocated on
a8833b0b, not the analysis's 426eb6ea. No implementation, tests, game operation,
push, or merge is part of this task. Code, test sources, and gzip capture data
were read; **no policy replay or test was executed**. “Base behavior” below is
the reachable code behavior with the stated reconstructed boundary state, not
a claim that a replay passed.

## Decisions that govern the change

- 09-17 identify-staff-20-mandatory: 「10F以降は鑑定の杖20回分が必須・調達不可なら採掘」.
- 09-17 departure-conditions-carried-only: 出発条件に自宅のアイテムを含めない（自宅は調達可能性の判断にだけ使う）.
- 10-03 identify-staff-max-four: 鑑定の杖は4本以内・少ない杖から手放し回数の多い杖に買い替え（20回分は維持）.
- 10-04 home-full: 自宅が満杯なら余り物を売って空ける・売れる品が無ければ自動破壊の対象→最安の不要品を壊す.
- 10-05 stockout-mining-timepass: 品切れだけで出発できない時は採掘で時間を潰して再挑戦（+5,000Gか1回分、3回で停止）.
- 10-08 black-market reserve: 闇市の任意購入は必需品1回分の補充代を常に残す.
- 10-09 sale-no-preempt: 装備の売却は入れ替えに割り込まない・満杯で入れ替え失敗なら今の装備で出発＋記録.
- 10-10 empty Identify surplus: 「空の杖は自由に売って良い」. Home-full
  relief and swaps may take empty staves to sell at Magic or another accepting
  store, otherwise destroy under the 10-04 ladder. The four-staff cap must
  neither refuse this transport nor pre-empt its disposal.
- Ownership contract (09-23/09-26): town errands have equal rank, no pre-emption; a stop that is a defect must stay
  visible (do not turn a stop into silent waiting or wandering).

The last decision forbids solving this by making Identify a higher-ranked town
owner. Continue a completed store operation at its release boundary, through
the existing store visit and buy/sell delegation. An unposted future Home
request may remain queued while this visit finishes. A posted Home take,
equipment mutation, sale, or purchase retains its confirmation ownership.
Do not relax departure readiness or reopen a closed supplier repeatedly.

## Current boundaries and common contract

| Boundary | Functions and base lines | Predicate/problem |
| --- | --- | --- |
| One purchase head | `policy_shop.py:_next_purchase` 2273, `_next_purchase_unreserved` 2915, `_legacy_next_purchase_unreserved` 2948 | Earlier wanted ware hides later Identify rung; filtering a returned head to `None` does not enumerate the next rung. |
| Churn | `policy_shop.py:_shop_core` 4823-4832 | `(item.tval, item.sval) in _town_visit_sale_signatures and not _identify_staff_swap_purchase(item)` returns ESC with `shop:sell-rebuy-churn-defect`. |
| Completed equipment disposal | `_shop_core` 4273-4286; `policy_instore.py:_in_store_selection` 205-207 | Pending disposal with `_pending_disposal(snapshot) is None` is cleared but emits ESC; pure preflight labels even this completed disposal as keyless `disposal`. |
| Atomic refusal | `_atomic_shop_transaction_key` 5601, cached result 5653-5655, settlement 5763-5843; `policy_observation.py:_resolve_observed_uncomposable_stop` 1161 | A non-buy/non-sell refusal can mark the supplier attempted and remove its claim although an affordable required staff remains. |
| IST continuation | `policy_instore.py:_in_store_entry_key` 395, `_in_store_selection` 193, `_in_store_emit` 442 | Selection/old-path ownership/preconditions or a prior producer's ESC end the entry before buying. |
| Relief before IST | `policy.py:_decide` 10185-10200 and 10351; `_shop_core` 4089-4094 | The Home relief producer runs earlier than IST; protecting only `_in_store_entry_key` cannot fix the sale-effect page. |
| Relief exit/refresh | `policy_home.py:_home_full_relief_key` 589, sale-effect branch around 826-862; `_home_full_knowledge_key` 1081-1096 | Confirmed relief sale decrements remaining and requests `leave_foreign_store=True`, emitting `home:scan-leave-store`. Queue/transport leaves elsewhere in relief have the same hazard. |
| Relief take filling staff cap | `_home_full_sale_candidate` 328, `_home_full_discard_candidate` 418, `_home_full_relief_key` catalogue selection 921-1059 and pending refiling 870-909 | Charged relief transport can occupy required capacity; empty surplus transport must finish sale/destruction before purchasing. |

Introduce a shared, **pure** `_departure_blocking_page_purchase(snapshot,
exclusions=...)` in `policy_shop.py`. It answers whether this actual page has a
legally selectable departure-blocking buy, independently of the legacy head.
It returns the actual `StoreItem`, its matching purchase provenance, and
quantity; it never emits, rearms, files Home work, or advances the plan.

Use `_purchase_rungs` / `_matching_live_purchase_rungs` (2636/2748) and
`_live_purchase_need` (2618): a match is required only if its live `NeedSpec`
is `departure_blocking`, resolves to this supplier, and is not satisfied.
Inspect both supplier occurrences for Identify, not just the first registry
entry. Do not infer requiredness from an active tail/optional rung alone.
Keep the established rung order among required candidates; within Identify
keep F4's maximum-charge, first-shelf-row tie rule. `_mandatory_purchase`
(2858) alone is insufficient: it has no Identify-staff branch.

For Identify the explicit predicate is: ordinary supplier (Magic/BM), live
Identify requirement, `not _identify_staff_ready(snapshot)`, count > 0,
`tval == TVAL_STAFF`, `sval == SV_STAFF_IDENTIFY`,
`max(charges,pval) > 0`, `_identify_staff_purchase_room(snapshot)`, and
`_identify_staff_acquisition_worthwhile(snapshot,max(charges,pval))`.
Then require a positive `_purchase_quantity`, cost <= current gold,
`_store_purchase_fits_pack`, existing fundraising reserve policy, applicable
BM reserve cap, availability/claim permission, and the same Home gate as the
ordinary buy. A Home BLOCKED verdict remains its existing visible stop; a
genuine HOME_FIRST verdict is a lawful procurement continuation, not a buy.
Use the already-rearmed HOME_FIRST fallthrough rule consistently in preflight
and emission. Neither a cap release nor a promised future sale supplies room
until its effect is observed.

Factor the existing buy emission tail (`_shop_core` 4833 onward) into one
shop-buy producer, proposed `_shop_purchase_key(snapshot, selection)`, rather
than writing a second purchase macro in the atomic fallback. It retains Home
arbitration, current row/quantity validation, stuck and no-progress counters,
purchase watch, execution offer, and typed provenance. Both ordinary selection
and in-shop required continuation use it. Pure preflight must return the same row as
this producer; it must not call `_shop`.

For F3 also expose pure `_departure_blocking_page_operation`: either the above
buy, or this visit's own pending release inscription/sale. The release predicate
is an unready Identify requirement, a nonempty `_identify_staff_release_plan`,
the selected release item legally sellable at **this** store, and a strictly
fuller affordable replacement on **this** page. Validate that the pack would
accept the replacement after the indicated release; the returned next action
is still the inscription/sale, never a speculative buy. This predicate protects
an entry at cap four before its sale, when the buy-only predicate is correctly
false. An unrelated pending disposal is not a release operation.
While a selected required buy is posted and awaits confirmation, retain its
same-entry operation identity for the relief guard without authorizing a
second emission. Route the pending phase through existing effect confirmation;
only a confirmed effect or bounded failure releases it to Home refresh.

## F2: skip churn and compose the surviving required operation

### F2(a): exclude the rejected ware, continue selection

Move the churn predicate into shared purchase eligibility, used by
`_next_purchase`, legacy selection, IST preflight and the required-page helper.
The existing `_town_visit_sale_signatures` remains the authority for **confirmed**
sales. `_identify_staff_swap_purchase` (3967) remains the strictly-fuller staff
exception, using `_town_visit_sale_identify_charges`; equal/emptier staves are
still rejected. Do not globally whitelist the Identify class.

Selection needs an explicit excluded-row/class input, applied **before** each
legacy `next`/`max` in the helpers receiving exclusions; other delegated
helpers have their returned head checked before ladder admission. Thread that
input through `_legacy_next_purchase_unreserved`, `_mandatory_purchase`,
`_mana_food_purchase` (`policy_supply.py:911`), and the two Identify rungs
(3140-3150, 3326-3345). For the other delegated `*_purchase` helpers (curse,
restore, quest carry, destruction, BM optional, launcher enchant), keep their
signatures and re-run the ladder with a rejected head's class added to the
local exclusion set. At each such rung, ignore a returned excluded class and
continue to subsequent rungs; re-running must never restart indefinitely at
the same excluded head. Otherwise 224534's rejected wand
is selected again through the mana-food helper. Do not replace the observed
store with a fictitious empty/filtered page: retain the full page for charge
comparison, Home/pack gates, reserve pricing, stockout and shelf evidence.
Only the candidates enumerated for this selection are filtered. Do not change
retention's `_item_matches_purchase_rung` into a buy-exclusion check.

Add `purchase_churn_exclusions` to `TownVisitLedger` (`policy_types.py:410`),
keyed by `(store_type, _item_signature(item))`. A stateful selection commit
adds each rejected signature once and logs `sell-rebuy-churn-skipped`; pure
preflight calculates the same exclusions locally without changing the ledger.
Also retain a `(store_type,tval,sval)` class exclusion for the sold-class
predicate: a different charge/count/name rendering or shelf letter cannot
evade it. Consult the strict-fuller Identify exception before class rejection.
The signature detail is diagnostic; the class exclusion provides the bound
across changing displays and a second similar shelf row. Key neither exclusion
by gold nor decision sequence. Normalize missing fields in
`policy_state.py:normalize_policy_state` (ledger defaults around 367).
Give the exclusions the same lifetime as sale signatures: clear both signature
and class exclusions beside `_town_visit_sale_signatures.clear()` and
`_town_visit_sale_identify_charges = None` at `policy_observation.py:768-771`,
under `snapshot.floor_key != self._floor_key` (752). The ledger replacements
at 101/123 are not the sale-signature reset sites; do not use those as an
independent exclusion epoch. No store exit, Home scan, purchase, plan cursor,
or independent ledger replacement may discard a still-live sale epoch's
exclusions (preserve/transfer them with that epoch if a ledger is replaced).
Honor restored exclusions only for replay/test checkpoints, with missing-field
defaults in normalization. Neither exclusions nor sale signatures survive an
autorecover restart: `scripts/bot_autorecover.py` resumes a fresh process,
without a checkpoint. The per-visit bound is per process, exactly as today's
churn guard; this task adds no persistence subsystem.
Do not mutate nested ledger sets inside `_in_store_pure_scope`: that context
restores attribute rebindings and diagnostics, not nested in-place mutations.
Commit exclusions only after stateful admission; extract side effects out of
the enumerator, including mana-food Home request writes, rather than assuming
the existing shallow scope makes new ledger mutations pure.

Continue the established ladder with X excluded, not an ESC/WAIT. On 224534
both MM wand rows `k` and `l` belong to the sold class: skipping only `k` would
buy `l` and reintroduce the pair. The next surviving Identify rung selects `o`.
An eligible earlier distinct required item may still be bought first.

**Bound:** one insertion per `(store,signature)` and one class latch per
`(store,tval,sval)` per visit; a selection pass visits each shown candidate at
most once (at most page-item count class additions); each re-run either adds
a new rejected class or returns/exhausts the ladder. Thus the unchanged helper
signatures cannot create an unbounded skip. Sales still use retention,
`_town_visit_purchases`, confirmed-sale signatures and the current sale attempt
guards. Preserve `town_visit_report` as the skipped churn diagnostic. When
no surviving wanted operation exists, keep the established churn defect
outcome for a churn-only page; do not convert a genuine defect to quiet waiting.
That conditional preservation limits incompatible old-test changes.
Sell/rebuy across visits separated by a dungeon trip remains possible
(`_find_device_sale` versus `tail:mana-food`); record it as a follow-up,
bounded by real progress, not as solved by this town-visit exclusion.

### F2(b): completed disposal releases to the required purchase

In `_shop_core`, when `_pending_disposal_item is not None` and
the target is absent from pack (`_pending_disposal(snapshot) is None`),
`_home_pending_item != _pending_disposal_item`, and
`_home_atomic_withdraw_pending is None`, clear disposal once, then check the
shared required-page selection. If it exists, fall through to its buy producer
instead of emitting `equipment:sale-complete`/the equipment exit offer.
If none exists, retain the current exit. Do not `return None` from `_shop_core`
here: that exits the dispatcher rather than continuing its buy tail.

Mirror this in `_in_store_selection`: a **completed** pending disposal is not
keyless `disposal`. A live disposal target or pending approved Home disposal
does not vanish merely because a staff is on the shelf. All three completion
conditions must be shared by preflight and stateful emission. A Home-sourced
dominated armour target can be absent from pack before withdrawal
(`policy_home.py:4237-4241`); that is live disposal, not completion. Continue only at a
released operation boundary; never discard a posted sale or its confirmation.
Seed the 040900 s42 regression by `_begin_pack_dominated_launcher_disposal`
(`policy.py:14794-14812`) with the sold item's actual slot/signature, then
construct the target-absent completion board. Add a Home-sourced dominated
armour control with matching `_home_pending_item` and a pending atomic Home
withdrawal control; neither clears. Use actual producer state;
do not patch `_pending_disposal` to return None.

**Bound:** disposal clears once; subsequent selection cannot rediscover the
same completed disposal from this marker. Purchase is bounded by the existing
buy watch and `STORE_STUCK_LIMIT == 8`. No supplier rearm is added.

### F2(c): atomic settlement veto, without a second mutating producer

The recoverable predecessor reasons are explicitly
`shop:sell-rebuy-churn-defect` (F2(a)), `equipment:sale-complete` (F2(b)),
`home:scan-leave-store`, `home:full-leave-with-surplus`,
`home:full-queue-surplus-withdraw`, and `home:full-space-ready` (F3(b)).
Recovery lives inside `_shop`: eligibility/completed-disposal/whole-relief
entry yield must select the buy before those refusals are produced. Therefore
`_shop` returns the buy directly for a lawful successor; the cached refusal
at 5653 never carries these recovered cases. F2's HEAD implements the first
two; F3 adds relief recovery without changing this atomic contract.

Do not invoke `_shop_purchase_key` after a refusal `inner`: `_shop` may
already have filed a Home errand, pending item and execution offer
(1048-1057). Composing a second producer on top is forbidden. There is no
post-refusal composition path or claimed fallback-only boundary in this design.
A direct buy from `_shop` uses the existing `inner.startswith(BUY_KEY)`
composition path: entry `5`, `shop:one-shot-buy`, and `p...ESC` tail.
A cached result is consumed once; never call `_shop` again on the same page.

Before non-operation settlement, use the pure
`_departure_blocking_page_purchase` with current pack/gold and the actual
observed page. While it is non-empty, do not call
`_resolve_observed_uncomposable_stop`, record `nonhome_attempted_without_effect`,
advance/block the plan as exhausted, discard `_shop_observation`, or mark the
need satisfied. A released refusal with this lawful required purchase is
`town:blocked:shop-required-operation-uncomposable`, published through the
existing `_town_blocked_key`, with cause `composition-mismatch`; no second
purchase emission occurs. If the helper is empty, retain today's settlement.
Preserve specific Home BLOCKED, genuine HOME_FIRST, ownership and breaker
outcomes. A genuine in-flight owner retains its existing confirmation budget;
a posted input tail is never bypassed for this stop or a replacement buy.

**Bound:** one `_shop` result per observation generation, followed by either
its existing composition, a pure settlement veto and visible stop, or existing
exhausted-page settlement. No recursion, retry producer, supplier rearm or
attempted-store latch reset. Optional BM buys cannot bypass the reserve.

## F3: finish the sale-to-buy continuation within its store entry

### F3(a): confirmed release sale, then buy on the fresh page

Reuse `_identify_staff_release_plan` (`policy_supply.py:743`): at cap four,
not ready, release the emptiest only if the observed affordable offer is
strictly fuller; above cap, release excess under its existing retention rules.
Do not change the readiness or release arithmetic. The selector at four is
correct to have no purchase room: sale is the next operation.

On the **same entry's fresh confirmed sale page**, let `_in_store_entry_key`
continue with the shared required buy ahead of another unrelated sale or
Home census. Recompute shelf letter, count, pack fit and quantity after the
sale. `_in_store_effect_confirmed` (617) already clears pending and increments
ops; `policy.py` 8310-8345 already verifies the tagged sale and calls it.
Do not claim that `_batch_sell_key`'s internal ESC at 3853 is always an emitted
exit: observation uses it to reconcile and ignores that return.

Inscription is a separate confirmed page operation, not a sale. Preserve the
`continuing=True` own-inscription carveout in `_in_store_preconditions` (285).
For a release transaction, allow its own pending inscription/sale to proceed;
an unrelated old-path watch remains a veto. Do not synthesize an effect to
make `ledger['pending']` disappear. The 040322 capture specifically needs this
inscribe -> sell -> observed sale -> buy path, not a direct purchase at cap.

No relaxation of `ended`, breaker, screen verification, page zero, entry
identity, no-effect rule, or eight-operation entry ceiling. If a required swap
still needs an operation at a defect/budget boundary, keep the stop visible
through the new typed final reason; do not reset ops to squeeze in another
transaction. A no-effect sale exits/stops without retrying the same sale.
Without IST enabled, keep the existing observed-page/one-shot lifecycle; do
not append a guessed buy after a sale in one blind macro. F2 still protects
its next correctly observed affordable purchase.

**Bound:** `_in_store_entry_ledger['ops'] < STORE_STUCK_LIMIT` for the same
`opened_sequence`; pending operations receive one own post-operation check.
Successful at-cap swaps strictly increase kept charges, the 20-charge target
stops supply acquisition, buys stay at <=4, and purchased items retain the
existing sale protections. A lower-charge staff cannot replace a higher-charge
one through the churn exception.

### F3(b): account once, then yield the whole ordinary-store relief dispatch

Use one shared relief-entry guard in `_home_full_relief_key`, covering both
call sites (`_decide` 10185-10200 and `_shop_core` 4089-4094). Separate its
one-time observed-sale accounting from subsequent relief work: first reduce
`remaining` once, clear `sale`/`withdrawn`, finish the relief errand and
invalidate Home knowledge (827-857), including completion/retry-deposit state.
Then evaluate the guard before any foreign-store exit, knowledge request,
WAIT, catalogue selection, pending refiling or new Home request/offer.

Guard = fully rendered lawful ordinary store page + live IST entry ledger for
this visit + non-empty `_departure_blocking_page_operation`. The entry must
match store/`opened_sequence` and respect page zero, screen verification,
`ended`, breaker, leave-inflight and pending-operation confirmation. At the
existing operation ceiling a still-required operation gets the defined visible
stop, never a relief trip which resets its entry. The predicate uses F2's churn eligibility and
current pack/gold; mere stock or an unsatisfied need is insufficient.
Return None from the relief dispatcher on this guard, handing the same
decision to this entry's existing IST continuation. It emits no key/reason,
Home-scan offer, staged macro, or new errand. This is equal-rank release,
not pre-emption of an active posted operation.

The same entry guard must run on every following same-page decision, even
with `sale=None` and `_home_knowledge_current=False`: otherwise 919-921
requests `_home_full_knowledge_key(snapshot)` with default
`leave_foreign_store=False`, and 1070-1077 accepts the ordinary shop page for
`~9\x1b` or `home:scan-await-observation`. Guarding leave sites or only
`_home_full_knowledge_key(leave_foreign_store=True)` is insufficient.
The whole-dispatch guard covers `home:scan-leave-store`,
`home:full-leave-with-surplus`, `home:full-queue-surplus-withdraw`,
`home:full-space-ready`, the knowledge macro, WAITs and catalogue selection.
It does not introduce a standalone knowledge-helper yield/return-type change.

Preserve remaining work, deposits, relief sale targets and deferred catalogue
refresh. Once the bounded IST operation is confirmed and no legal required
operation remains, resume Home census under its existing owner. A composed
ordinary store page may use this guard only with a genuinely live matching
IST ledger; do not invent one to force yielding. Other pages retain the
existing scan/exit lifecycle and active-owner protection.

**Bound:** observed disposal decrements `remaining` once, never on yield;
`ops < STORE_STUCK_LIMIT` and no-effect/entry-limit visible-stop rules still
apply. The S11 pin covers both the confirmed-sale decision buying and a
constructed following same-page decision with buy pending and invalid Home
knowledge: no `~9`, WAIT scan, leave or catalogue mutation; preserve buy
confirmation ownership without issuing a duplicate buy. After a constructed
confirmed buy, deferred Home refresh resumes if no required operation remains.

### F3(c): reserve capacity against charged relief; finish empty-surplus disposal

Add pure `_home_full_relief_take_blocks_identify(snapshot,item,quantity)`.
For **Home-source relief transport**, reject only when the item is a CHARGED
Identify staff (`max(charges,pval) > 0`),
`not _identify_staff_ready(snapshot)` and
`sum(staff.count for staff in _carried_identify_staves(snapshot)) + quantity
>= STAFF_IDENTIFY_MAX_COUNT`. Count actual units, not stacks, and use the
whole queued take quantity (currently often `item.count`). A two-unit take
from three carried staves is rejected, not clipped to a temporary over-cap
take. This restriction is on relief, not legitimate charged staff procurement.

Apply before sale/discard/identify candidate ranking in `_home_full_relief_key`,
before `_file_home_errand` and `_home_pending_item` assignments, and when
refiling an old relief `sale` that has not been withdrawn. Revalidate an
already queued **unposted** `full-home-sale`/`full-home-discard` take at the
atomic Home withdrawal dispatch (`policy_home.py:_atomic_home_withdraw_dispatch_key`),
so a restored or previously queued request cannot evade the filter. Retire
only this rejected relief request at its release boundary; do not cancel an
already posted Home macro. Observe a posted take normally, then use the
release-sale continuation on the supplier page.

Record the candidate's visit-local relief skip (`relief['skipped']` and
`skipped_home_counts`, existing skip machinery), with diagnostic cause
`identify-cap-reserved`. Do not label it permanently unsellable or mutate the
Home approval file. Reconsider only after real relevant capacity/readiness
change, not price/gold/turn changes. A ready character's relief behavior stays
the same. Carried-source relief which reduces the staff count is unaffected.

Use the existing skip ledger format but separate bookkeeping from
`_home_full_skip_key`'s emitted `WAIT_KEY`/`home:full-skip:*` path. An unposted
candidate rejected here neither changed shelf addresses nor needs a knowledge
invalidation. Record it and select the next legal candidate within this bounded
selection pass. The relevant capacity fingerprint is carried staff count plus
Identify readiness, in addition to the recorded Home target count; only its
change permits reconsidering this cap skip. Do not emit a WAIT on an ordinary
store entrance just to record the exclusion.

Empty Identify staves (`max(charges,pval) == 0`) are surplus under the 10-10
owner decision and bypass this relief-take cap rejection entirely. Take the
whole lawful selected quantity to sell if Magic or another store buys it;
otherwise use the 10-04 auto-destroy/cheapest-unneeded ladder and its existing
pack-destruction confirmation. No one-staff limit, readiness condition,
fuller-shelf condition, or charged-count ceiling is added to this permission.
Pack capacity, address authority and genuine unrelated posted ownership still
apply. Hengband requires taking the Home item before sale/destruction; do not
invent direct Home shelf commands.

Count every carried unit, including empty staves, in the existing acquisition
room/cap arithmetic throughout take->sell/destroy. Do not globally exclude
empty staves from `_carried_identify_staves`, readiness, purchase-room or
release-plan calculations. The exception is permission to transport surplus,
not room for a speculative buy: three + one may temporarily fill four, and
four + two may temporarily reach six. No charged acquisition is allowed while
actual carried count lacks room. Above-cap/at-cap supply routing must allow
this admitted empty-surplus disposal to finish under its current owner before
any cap-triggered refile, equipment/Identify acquisition or Home census can
pre-empt it. Match the observed withdrawn target/quantity to the existing
relief request and sale/discard watch (using release delegation when relevant);
do not treat its empty target as a needed staff, send it back Home, or wait
for a fuller offer. At cap with no fuller offer, the normal release-plan rule
is not permission to veto the independently lawful relief sale/destruction.
After the observed disposal, recompute actual count, charges, shelf address
and purchase room; only then resume required acquisition. Pending/unconfirmed
sale never supplies room. A no-effect disposal retains the existing bounded
visible failure, never silently loops or triggers a guessed purchase.

For charged targets rejected by the cap predicate, continue the ordinary
10-04 relief ladder: another lawful sellable surplus, then legal destroy
candidates. Apply the charged filter to sale/discard/identification transports,
including queued unposted takes. Unknown items still require identification;
protected charged staves and owned gear remain protected. If only rejected or
protected targets remain, retain existing defer/no-legal-relief and required
blocker outcomes. Empty-only Home stock is not such a cap-rejected set.

**Bound:** rejected `(signature,Home count)` remains in the relief skip ledger
for this capacity state; this applies only to charged targets. Empty transport
is bounded by real take/sale/destruction confirmation, not a capacity skip.
A no-candidate pass defers the batch rather than
re-filing it. Existing `remaining`, errand attempts and destruction confirmation
budgets still apply. No Home<->Magic take/sell pair can reset the skip.

## Verified capture pins and what F1/F4 already changed

All source files below are in `C:/hengband/bot-client/jsonlog/`. Row numbers are
one-based physical gzip JSONL lines, including nondecision rows. “s” means
`decision_sequence` in the **last session**, not a JSON field named `step`.
Use boundary replay with declared owner/watch/ledger seeds: the captures have
no policy checkpoint. Stop historical playback at the first changed key;
subsequent effect boards must be declared constructed and validate inventory,
gold, stock letters, sender and claim ownership. Raw historical assertions
remain historical assertions after implementation.

| Capture basename (append `.bot-decisions.jsonl.gz` / `.bot-state-fixed.jsonl.gz`) | Verified boundary and historical key/reason | Base a8833b0b status and expected changed result |
| --- | --- | --- |
| `autorecover-20261007-224534-town-blocked-owner-retired-burst` | D69 s41, turn 15003859; S21 Magic, gold 29994, carried 2+1 charges, shelf `o` 822/19 x2 and `p` 742/13 x4. Historical ESC / `town-progress-invariant:continue-observed-shop`, IST `home-first` for `k` MM 394/40. D70 s42, turn 15003865: key `7` / `town:entrance-step-off:town:unsafe-recall-fallback`; selector refusal `shop:sell-rebuy-churn-defect`, settlement `shop:observed-operation-uncomposable`. S22 is the outside board. | **Drop the Home-first subpin**: F1 excludes empty Home devices. Keep the churn subpin, seeded from confirmed wand sale signatures; F1 does not change that guard. Expected IST `po...` / `shop:in-store-buy` (quantity from current selector); outside-composition control: `5` / `shop:one-shot-buy`, staged `po...ESC`, no settlement. Both `k` and `l` MM rows must be skipped. |
| `autorecover-20261009-040900-town-blocked-departure-unsatisfiable` | Last session D88 s42, turn 16117545, S42 Magic: 51341G, three 1-charge staves, `l` 830/20 x2. ESC / `town-progress-invariant:continue-observed-shop`, IST `disposal`. D89 s43, turn 16117553, travel key `ESC\u0060n(.` / `shop:travel`; selector refusal `equipment:sale-complete`. | Keep: F1/F4 do not clear keyless completed disposal. Seed `_begin_pack_dominated_launcher_disposal` with the sold launcher slot/signature on a declared pre-sale board, then use S42 with target absent and both Home completion guards satisfied; include the live Home-sourced disposal control. Expected s42 direct `pl1\r\r` / `shop:in-store-buy`; outside-only control at s43: `5` / `shop:one-shot-buy`, `pl1\r\rESC` tail. No equipment exit offer, no supplier settlement. |
| `autorecover-20261009-014739-town-blocked-owner-retired-burst` | Last session D92 s27, turn 15849156, S44 Magic: 14355G, zero carried staves; `g` 830/20, `h` 777/16 x2, `i` 623/20 x1. ESC / `town-progress-invariant:continue-observed-shop`, IST `disposal`, no-old-path-operation false. D93 s28, turn 15849160: `Cf\ryESCESC` / `periodic:character-dump`, selector refusal `home:full-queue-surplus-withdraw`; another Magic row S49 at that turn. | Keep relief and old-path ownership pin: neither is fixed by F1/F4. Do not pretend the periodic key is the refused shop key. On a declared constructed continuation board copied from S49 (not a historical reconciliation row), with `_store_visit.operation_posted=False` only after the prior watch is genuinely reconciled and all old input/watch state released, composed required buy is `5` / `shop:one-shot-buy`; current F4 max-charge/first-row tie picks `g`, so tail `pg\rESC`, rather than historical cheapest `i`. Direct IST control `pg\r` / `shop:in-store-buy`. A live posted old operation remains owned until confirmation/bound; it must not be bypassed to force this expectation. |
| `autorecover-20261009-040900-town-blocked-departure-unsatisfiable` | Last session D69 s23 `d0y` / `shop:in-store-sell`, S10 pre-sale 53370G, four staves; D70 s24 ESC / `home:scan-leave-store`. S11 same turn 16116698 is the **observed sale effect**, gold 53565, three 1-charge staves, shelf `l` 830/20 x2 plus sold 0-charge `m`. | Keep: F1/F4 do not change relief's early foreign-store exit. On this same confirmed entry S11, expected `pl1\r\r` / `shop:in-store-buy`; deferred Home refresh resumes after its observed buy. Assert relief remaining decremented once and own IST sale pending cleared, not patched away. Two-decision pin: next use a declared constructed same-page board with the buy pending, `sale=None` and invalid Home knowledge; it must preserve buy confirmation ownership and emit no `~9`, scan WAIT, leave or new Home work. Then construct the confirmed buy effect for refresh resumption. |
| `autorecover-20261009-040322-no-key-exhausted` | D138-144 s37-43. S62 -> S63 at turn 16115767 confirms `{o@0\r` / `shop:in-store-inscribe`; s38 ESC / `shop:in-store-done`. Carried three 1-charge + one empty staff, gold 53792, `l` 830/20 x2. s39 `01kb` / `town:destroy-overflow`; s40 entry `5`; s41 ESC / `shop:observe-and-leave`; s42 `5` / `shop:one-shot-sell` with IST operation `d0y`; s43 ESC / `shop:in-store-done`. S67 and S70 still contain the empty tagged staff. | Keep, but **correct the analysis**: a sale was posted at s42; its effect is not present. Expected first divergence after confirmed inscription S63: `d0y` / `shop:in-store-sell` within this entry, then only on a constructed confirmed-sale page `pl1\r\r` / `shop:in-store-buy`. Never claim historical S70 is a sale effect or expect a buy while still at cap. Separate unchanged-inventory/no-sale-effect control ends visibly without retry. F4's no-room rejection is correct and must remain. |
| `autorecover-20261007-184438-town-blocked-owner-retired-burst` | D4 s11, turn 14552417: `5pj2\rESC` / `home-errand:atomic-withdraw:full-home-sale`; D1/D3 already queue relief. The state file begins later at turn 14553799 (S1), then shows three carried staves, 11 charges; its later S48 Home knowledge is at turn 14554316. **There is no matching s11 state row or pre-take Home page.** | Keep decision-only evidence. The s11 diagnostic gives four staves (1, 3, and 2x4 charges), not later S1's three/11 state. Construct that four-staff pre-take boundary plus a two-unit empty target at `j`, with fresh address authority. The entire Home catalogue, `_home_full_relief` (`mode`, `stock_count`, `deposits`) and `_home_knowledge_current=True` are constructed: no historical Home page/s11 state supports them. Under the 10-10 decision, expect `5pj2\rESC` / `home-errand:atomic-withdraw:full-home-sale`, no `identify-cap-reserved`; then construct take and sale effects (temporary six -> four), with no acquisition before sale confirmation. No Magic purchase claim follows from this capture. Primary F3(c) pin is the separate three + one empty control below; this is decided behavior, not a regression preserving old cap rejection. |

Name/docstring the 184438 test as a **constructed Home-state empty-surplus
transport control anchored to the 184438 decision only**. Provide a full
constructed relief dictionary, including `mode="sale"`, `stock_count`,
`deposits`, `remaining`, `sale`, `withdrawn` and skip fields as needed, and
`_home_knowledge_current=True` with declared catalogue/address authority.
The empty target is the eligible surplus; no alternate potion is required to
avoid it. Check the real atomic dispatcher at the Home entrance and observed
withdrawal, then the accepting-store sale of the complete two-unit target.
With an unchanged sale-effect board, assert bounded visible failure, no rebuy,
no refile Home, and no repeated withdrawal.

The **primary three-plus-one control** constructs three charged carried staves,
one empty Home staff, a full Home catalogue/relief state and fresh address.
Expect the empty take and its sale at cap four even without any fuller supplier
offer; after observed sale count is three. Add the unsellable-at-all-stores
variant which follows the 10-04 destruction ladder, with actual take and
confirmed pack destruction. Also cover multiple empty staves (N=3,q=2 and
N=2,q=2), already N>=4, and readiness both ways: no quantity/readiness/offer
restriction on empty surplus disposal. These are the owner's decided behavior.
Contrast with charged q=1 at N=3 (and charged over-cap q=2): while unready,
reject with `identify-cap-reserved`, choose a legal alternate if present,
otherwise defer visibly. A ready control retains existing charged relief.
No tests may infer the constructed Home state from the later S48 catalogue.


**Fixture correction:** `tests/fixtures/identify-staff-stockout-20261007.json.gz`
does exist, but its `board_rows['magic_shop']` and `['after_magic']` equal source
state rows **69 and 70**, turns **15004409 and 15004415**, not s41/s42's S21/S22.
The analysis/design-1 assertion that the fixture contains the s41/s42 boundary
(or rows 68/69 for it) is incorrect. It remains useful supplier evidence and
`test_recorded_worthwhile_magic_offer_keeps_a_live_owner` remains valid; extract
S21/S22 and D69/D70 for the new churn pin instead of silently relabelling the
existing fixture. No requested whole F2/F3 pin is already fixed by F1/F4; only
the 224534 Home-first component is dropped.

For reproducible future extraction, source compressed-file SHA-256:

| Stamp | decisions | state-fixed |
| --- | --- | --- |
| 224534 | `9dfea54aae58ffdf53ea348fbabc183e9758cc1efc947ae45e3fd8b06d964468` | `d49360c567ff8eaa25e0777e507827f8aa82c64ff5b341d2d35146a9d4287475` |
| 040900 | `8b98eb15335a482c8d2644a5e02f59103507db01ee5e4c419e75df26e6a54c4e` | `224b4db9d192108735f156ecef288ab6ace5847fa669d6245794cab079b235c4` |
| 014739 | `da41071ab938ac8159c3a86ce7ed7eb8f1cfc263e550465b15c5cf5ba1e417b3` | `8b24f50d57e20e4f3789e923223b81676dafe8c8935eed5cad2d96845fe13a1f` |
| 040322 | `126cfb9e0a08242638f78f6fe58828825efdf595c97fa2139321f097532594b7` | `9ac298ab2f2af5acb3d0c22d84051ab3dd0677cb13e54243c17aef9f1b9d943a` |
| 184438 | `bcd6f4bb312a18f9d8e2bdccbdbaa1d242a6866d1b0f4cfa856af9297705cb74` | `30420b7c2617ae36968a1bfa06deb26b2a79655232a53670df80ac7ac4a79338` |

## Existing tests: old expectations versus decided behavior

Located by searching reason strings and inspecting their enclosing tests at
a8833b0b. These are compatibility decisions, not results of a test run.

| Module and test | Existing expectation | Decision |
| --- | --- | --- |
| `tests.test_policy_shop.ShopPurchaseSellPolicyTest.test_confirmed_digger_sale_arms_sell_rebuy_churn_defect` | `_shop` ESC, churn reason/report, on a churn-only General page (line 924). | Preserve: no surviving required ware. Add a separate two-rung control for F2(a); do not weaken this defect assertion. |
| `tests.test_crosstown_alt_recorded.CrosstownAltRecordedTest.test_recorded_before_cycle_and_actual_refusal` | `_observe_refusal` helper (84) expects IST preflight buy then churn refusal. | Preserve immutable history. Pure preflight now needs to agree with the stateful churn filter; split out/update the live-helper assertion. |
| Same module: `test_no_operation_settles_observed_shelf_even_after_plan_advanced`, `test_after_refusal_travel_reaches_recorded_target_without_reentry`, `test_terminal_refusal_is_not_reclassified_by_stale_home_knowledge` | Shared helper, atomic no-op settles/quarantines this sold Identify class even with moved cursor/stale Home. | This boundary seeds a sold staff class with no recorded fuller-sale exception. Preserve the no-safe-successor quarantine behavior; update the helper's preflight expectation. Add a distinct fuller-sale/required-successor boundary which must buy rather than settle. F2 does not authorize rebuying an equal/emptier sold staff. |
| `tests.test_identify_staff_swap_churn_recorded.IdentifyStaffSwapChurnRecordedTest.test_recorded_stay_is_the_incident` (test line 285) | Frozen historical `composition_refusal == shop:sell-rebuy-churn-defect`. | Preserve recorded history. This is not an assertion that changed policy must reproduce the refusal. Existing fuller-swap success controls must stay valid. |
| `tests.test_home_relief_progress_recorded.RecordedHomeReliefProgressTest.test_recorded_home_relief_remaining_prevents_owner_retirement` | Helper `observed_sale` line 49 expects ESC / `home:scan-leave-store` after each recorded relief sale, then constructed outside scan. | Conditional F3(b) change is decided: retain for pages without a legal required successor; if these source pages produce one under actual readiness, update only that action/effect segment and declare the new continuation. Keep remaining/progress/no-effect assertions. |
| `tests.test_home_relief_progress_recorded.RecordedHomeReliefProgressTest.test_home_relief_no_observed_space_effect_still_retires`, `test_home_relief_gold_alone_does_not_change_progress_vector`, `test_home_relief_requested_withdrawal_without_effect_does_not_reduce_remaining` | No-effect/only-gold controls (some inject reason labels rather than producing commands). | Preserve; changing labels is not observed work. |
| `tests.test_store_reentry_recorded.StoreReentryRecordedTest.test_unconfirmed_operation_leaves_without_retry` (848) | Own fresh unchanged board exits with `shop:in-store-done`, ops 0. | Preserve no retry. Required-operation defect branch gains the explicit final reason below; optional/no-required branch retains done. This is the decided visible-defect behavior, not permission to synthesize a buy effect. |
| Same module: `test_per_entry_bound_ends_the_entry` (1101) | At ops 8, ESC / `shop:in-store-done` although a sale remains. | Preserve ceiling; when this is a required swap with an eligible replacement, change the expected visible final reason. No budget reset. |
| Same module: `test_p9_visit_operates_in_store_and_closes_outside` (772), `test_p3_sale_then_buy_are_addressed_from_each_observed_page` (742), `test_p4_in_store_operation_clears_an_earlier_observation_of_the_shelf`, `test_b8_old_entry_cannot_confirm_on_new_entry_board` | Completed buy exits; confirmed sale buys from fresh shelf; observation/entry identity protects against duplicate composition. | Preserve. P3 already proves the simpler same-entry sale->buy path works on this base; F3 handles interfering relief/completed-disposal/own-inscription cases. |
| `tests.test_policy_shop.ShopPurchaseSellPolicyTest.test_in_store_selector_leave_ends_visit_with_nonterminal_reason` (306) | Empty shelf + mocked selector leave is done. | Preserve: no real required successor exists. |
| `tests.test_policy_home.RecordedStaleHomeScanInsideTest.test_invalidated_multi_page_home_leaves_before_scanning`, `RecordedErrandShoppingStaleHomeScanInsideRound2Test.test_live_errand_shopping_home_visit_exits_before_scan` | Exit Home/incomplete Home page before catalogue scan. | Preserve: F3 guard applies only to lawful ordinary-store continuation, not Home. |
| `tests.test_home_full_await_knowledge_recorded.HomeFullAwaitKnowledgeRecordedTest.test_recorded_sale_delta_scans_then_selects_next_withdrawal`, `test_071040_board_requests_scan_instead_of_recorded_escape` | Relief refresh after sale/outside, scan ownership. | Preserve outside/no-required cases. Add required-open-store control rather than silently replacing scan lifecycle. |
| `tests.test_absorbing_states.SeededAbsorbingStateTest`, `test_six_seeded_states_reach_progress_or_visible_terminal`, `test_seed_verdicts_depend_on_visible_bot_terminals` | `absorbing_state_catalog._town_sell_rebuy_churn_defect` (1640) expects churn-only terminal. | Preserve this churn-only seed and add a successor seed that must buy. Retaining a defect where no lawful successor exists satisfies the owner contract. |

Search found **no existing test assertion of `equipment:sale-complete`**, and
no test directly requiring a Home relief take to fill the Identify cap while
unready. F2(b) and F3(c) therefore need new boundary pins, not an old assertion
deleted under a broad “behavior changed” exemption. Existing sale-first tests
`tests.test_homefull3_recorded.ConstructedDiscardTest.test_D_sell_first_even_when_autodestroy_stock_exists` and relief disposal tests must continue to prefer **legal**
sales; charged cap-occupying transport is ineligible; empty transport remains
legal for sale/destruction under the 10-10 decision. Protect needed charged stock. Implementer must preserve existing F1/F4 regression pins and supply cap
tests (`test_identify_staff_stockout_recorded`, `test_identify_staff_procurement_step15d`,
`test_classC2_departure_recorded`, `test_policy_supply`, `test_live36_weight`).

Ledger-field compatibility work must include
`tests/test_town_progress_invariant.py:51` and
`tests/test_town_restock_trajectory.py:252`: these seed
`_town_visit_sale_signatures` directly on restored/private-seam policies.
Update their state shims for both signature/class exclusion state and the
shared sale epoch, and add `normalize_policy_state` defaults (367-370) for
missing ledger fields. Check a legacy checkpoint and seeded policy without
the new fields; no attribute failure or pure-preflight mutation is permitted.

**Checked, unchanged Home-side controls:**
`test_alchemist_observed_shop_alternation`, `test_oneshot_preempt_recorded`,
`test_policy_town:1361` (`observed-operation-uncomposable`), and
`test_home_full_relief_recorded:258`, `test_home_equipment_disposal`,
`test_destroy_procurement_guard` (`_pending_disposal_item`). These do not gain
an ordinary-store required successor by this revision; their Home ownership,
settlement and live-disposal expectations must not flip.

## Reasons, claims and future verification

Use existing action reasons: `shop:in-store-inscribe`, `shop:in-store-sell`,
`shop:in-store-buy`, `shop:one-shot-buy`, and lawful existing Home relief reasons.
New **diagnostic values**, not `last_reason` setters:
`sell-rebuy-churn-skipped`, `identify-cap-reserved`, and
`required-page-continuation` (include predecessor reason, store, signature,
observation generation, selected row/quantity and budget identity).
Home yielding has no emitted reason/key of its own.

One new final reason: **`town:blocked:shop-required-operation-uncomposable`**.
Use for a released legal required page operation which cannot bind after the
single continuation attempt, or a still-required swap stopped by no-effect,
entry limit, or selection/emission mismatch. Preserve specific existing Home
BLOCKED/ownership/breaker failures instead of overwriting them. Include a
structured cause (`composition-mismatch`, `sale-no-effect`, `entry-budget`,
etc.) and the actual page/operation in the report. Route the final stop through
the existing typed stop machinery, not a new poll loop.

Add it to `policy_constants.py:POLICY_FINAL_STOP_REASONS` (304) and the
`messages` table in `cli.py:_policy_final_stop_banner` (597+), with truthful
text such as "a required operation on the observed shop page could not be
completed within its existing transaction budget". Publish via existing
`_town_blocked_key`. `town:blocked` is already the registered town-plan prefix
(`town_arbiter.py:151`, `claim_goal_typing.py:447`), including
`town:blocked:overweight-surplus-rebuy-loop`: no new arbitration prefix or
shop-buy reason family is added. The
`tests/test_ownership_s2a_classification.py` digest must NOT change.
The factored `_shop_purchase_key` retains `@claims(ClaimOwner.SHOP_BUY)` or
an equivalent explicit claim scope and matching execution offer for the buy;
that ownership does not apply to the town-plan final-stop publication.
Retain existing dispatcher exception entries for `_shop_core`,
`_atomic_shop_transaction_key`, `_in_store_leave`, `_decide` in
`scripts/ownership_claim_exceptions.txt`; a new mixed dispatcher requires its
own justified entry, never a blanket exemption. `_home_full_knowledge_key`
already has `@claims(ClaimOwner.HOME_SCAN)`; its keyless yield must not declare
a conflicting buy. Shared selection/take predicates are pure helpers and
need reviewed census entries in `scripts/town_work_review.json` (the existing
F4 entry is `policy_supply.py:SupplyMixin._identify_staff_acquisition_worthwhile`);
update `scripts/town_work_registry_review.json` if registry expressions change; regenerate
`scripts/town_work_manifest.json.gz` and `src/hengbot/town_work_sites.json` during
implementation. Exclusion insertion/relief skip alone is not business progress.

Future implementation verification (not run for this design):

- F2: churn head plus next required rung; two MM rows same class; visit exits,
  Home scans, gold/name/letter changes cannot reset exclusions; completed
  disposal with/without required successor and live Home disposal controls;
  cached direct buy composes once, cached refusal never emits a second buy;
  moved cursor does not settle affordable required stock; genuine posted
  old operation retains ownership; Home BLOCKED/genuine HOME_FIRST controls.
- F3: confirmed inscription->release sale->observed effect->buy in one entry;
  relief remaining accounted once before continuation; no post-sale ESC or
  census before the required buy or during its pending same-page confirmation; refreshed shelf addresses/pack letters;
  no-effect sale and ops ceiling produce a visible stop, no extra attempt;
  duplicate outside composition remains impossible.
- F3 relief: empty disposal permitted for N=3 + q=1/q=2, N=2 + q=2 and
  already N>=4 without fuller stock; charged cap-fill rejection; queued unposted
  restored request, posted request observation, ready character control;
  alternate sale before legal destroy, no-alternate defer, no direct shelf
  destruction, unknown/artifact/transaction reservation retained.
- Regression: BM optional reserve and zero-charge/reliability/10F readiness
  unchanged; real no-worthwhile-stock mining still follows +5000G/one refill
  and three-attempt visible stop. Revert each new predicate/continuation
  individually and show its targeted boundary pin fails; do not mock selector,
  readiness or effect confirmation. CLI banner and ownership/manifest checks
  cover every new reason-setting site. Full-suite merge checks wait for the
  currently running suite to finish; this design task runs no suite.

## Implementation order

**F2 first, then F3 in a separate task on F2's resulting HEAD.** They can be
two reviewable/committed implementation tasks, but are not independent:
F3's preflight and post-sale yield must share F2's required-page selection,
churn eligibility, in-shop buy producer and atomic settlement-veto contract. F2 alone fixes
head/completed-disposal losses and unsafe settlement but not Home relief's early store exit or cap
transport. F3 alone would still hand its buy to the old churn/completed-disposal
refusal. Do not develop two independently mergeable selectors or new town
owners. The 040900 sale-effect pin exercises their combined boundary; split
fail-before/pass-after evidence by producer so a partial fix cannot claim it.


**Implementation task 1: F2 on a8833b0b:** implement F2(a), F2(b), F2(c), the
shared pure required-page selector, factored in-shop buy tail, exclusion state
and town-plan final reason. Pins: 224534 S21/D69-D70 churn (both MM rows),
040900 S42/D88-D89 completed launcher disposal, and constructed refusal with
required ware (visible stop, no second producer); retain churn-only and live
Home-disposal controls. Test list: `test_policy_shop`,
`test_crosstown_alt_recorded`, `test_identify_staff_swap_churn_recorded`,
`test_absorbing_states`, `test_town_progress_invariant`,
`test_town_restock_trajectory`, ledger normalization/checkpoint controls,
`test_ownership_s2a_classification` (unchanged digest), CLI final-banner and
ownership/manifest checks; preserve the listed F1/F4/supply/BM controls.

**Implementation task 2: F3 on task 1's committed HEAD:** implement own
inscription/sale continuation, the whole relief-entry yield after accounting,
and charged-only take rejection with uninterrupted empty-surplus disposal.
Pins: 040900 S11 two-decision pending-buy/refresh control; 040322 S63
inscribe->sell with constructed sale effect/no-effect controls; 014739 declared
S49-based reconciled constructed board with `operation_posted=False`; primary
constructed three-plus-one empty transport/sale plus no-fuller-stock destroy
control; 184438 decision-anchored constructed four-plus-two empty transport;
charged cap-fill alternate/no-alternate controls. Test list:
`test_store_reentry_recorded`, `test_home_relief_progress_recorded`,
`test_home_full_await_knowledge_recorded`, `test_policy_home`,
`test_home_full_relief_recorded`, `test_home_equipment_disposal`,
`test_destroy_procurement_guard`, `test_homefull3_recorded`,
`test_alchemist_observed_shop_alternation`, `test_oneshot_preempt_recorded`,
`test_policy_town`, and the unchanged F1/F4/supply/cap tests listed above;
repeat affected F2 pins and ownership/manifest/banner checks. Each task adds
its declared boundary controls and verifies targeted predicate reversions as
specified above. All of these are future implementation test lists; this
revision runs no tests and changes no code.
