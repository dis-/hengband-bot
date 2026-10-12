# Town errand idle: step 3 D / issue #1

Design only, 2026-10-13. Intended implementation base: `main 32f93f9c`.
Analysis checkout: `38c4d42c` (adds only the task to that base). No production
code, test code, test execution, game/bot control, push or merge accompanies
this document. Implementation and live qualification below are future work.

## Revision 2

2026-10-13; applies all six required changes in
`SOL-DESIGN-town-idle-20261013.review.md` and its three should-fix recommendations.

1. **Restart scope:** Shared accounting and measurement now use process-local,
   visit-local bounds only; no restart checkpoint/ledger. R7 ended through
   autorecover. The outer bounds are the existing same-reason 3-in-30-minute
   escalation rule and the measured at-most-3 town restarts/stops per 24 hours.
2. **Interrupted routes:** G3/G5/G7, Shared accounting and D2/D3 explicitly
   re-baseline at resumption after observed displacement by another owner,
   including misc/melee. No credit for the baseline itself; own-decision
   bounds remain. Survival alone does not split `_last_pair`.
3. **Evidence and mergeable pins:** Limits of causal proof and D1/D6 name
   both burst state captures and physical rows. D5 contains only R10's bound
   Magic operation; R4 is unclassified and excluded until independently pinned.
4. **Outside catalogue scan:** G1/G3 and D2/D4 use existing outside `~9` for
   catalogue-only work. A Home page supplies local transaction addresses,
   not additional catalogue content; transport is retained only for physical work.
5. **Test assertions:** Existing tests below include the complete current
   alias-search module inventory, per-slice green controls and explicit flips.
   Historical evidence assertions remain unchanged; no tests were executed.
6. **A/D boundary:** R14-R16 are unchanged, retirement correct, handled by
   step 3 A (`light-swap-1013`). D6 is one regression test on the 23:12:48
   capture after A lands; D adds no finite-light-choice rule. R13 stays in D;
   step 3 B affects none of the 16 records.

The three recommendations are addressed in D0 (retiring entry point,
recurrence key/count and `_last_pair`), the measurement gate (D0 starts the
clock; explicit idle thresholds), and G2 (post-forgiveness withdrawal ending).
Both owner questions are closed by the standing decisions above: no restart
memory, and A owns the light changes. No new owner approval is needed for this
revision. The later runtime enforcing switch remains a separate action.

## Decisions retained in full

These owner decisions govern this revision; the older design is background,
not permission to implement its discarded stages:

> 2026-10-05: 町の用事の打ち切りは直るまで記録だけ（止めない）＋前進の定義を全種類作り直す.

> 2026-09-23/09-26 ownership contract: 町の用事は同じ順位（横取り禁止）; 違反は停止; 前進は距離＋観測; a defect stop must stay visible (no silent waiting or wandering).

> 2026-10-09: 手順1は見張りの数え方の修正だけ・閉じる仕組み等は作らない (the earlier "close and remember" was dropped); 必須の用事の行き来は場面ごとに直す (step 1.5).

> 2026-10-03/10-09: 入れ替え失敗は今の装備で出発＋記録.

The landed slice-1 decision also retains the independent, count-based visible
stop at three retirements without productive admitted work in one visit. It
does not authorize turning every retirement back into a stop now. Do not
remove that burst stop to make measurements green.

No new town owners, priorities, departure gates or resistance/speed rules are
proposed. An active owner's finite continuation is handled by that same owner.
Failure of an equipment swap uses the existing current-loadout closure and
records its cause; all other departure conditions still apply. Mandatory
procurement failure stays visible. Optional work ends once with a record.
Neither outcome is an unlabelled WAIT or a walk without a purpose.

## Evidence and counting

Read: `PLAN-town-stability-20261009.md` (including its later owner decisions),
`STEP2-RESULTS-20261013.md`, the earlier design and adjacent review in
`evidence-d/`, and `evidence-d/STEP1.5-ANALYSIS.md`. Source references below are
one-based lines in this checkout, under `src/hengbot/` unless prefixed `tests/`.

The authoritative incident list is
`evidence-d/owner-retired-log-only-step2.jsonl`: 16 records, **12 CL45 + 4 low**.
They are disjointly grouped below, rather than counting a detector's replacement
both as a shop route and as a detector incident. The summary's CL45 categories
sum to 13; its shop category overlaps the detector replacement. This document
uses the 16 actual records, not that category sum.

All records have floor `[0,0,0]`, `progress=false`, `would_retire=true`,
`retired=true`, budget estimate 0. Fourteen are forgiven. R7 and R16 have
`forgiven=false`: they are the third retirement and cause a visible
`town:blocked:owner-retired-burst`, not harmless single retirements. R7's
loop was ended by the autorecover restart, not a restart-surviving work bound. CL45 rate
is 12 / 6.05 = 1.98 retirements/hour; low-level rate is 4 / 2.82 = 1.42/hour.
These are rates per run hour, not per hour physically in town. R4 remains
unclassified and is not evidence that its retirement was false.

Decision gzip files were read line by line, retaining only small neighbourhoods
of matching rows. No large decision log was loaded wholesale. Backup roots:

* H = `C:\hengband-backups\state-logs\step2-20261011\`.
* L = `C:\hengband-backups\state-logs\step2-lowlevel-20261012\`.

Time/turn/reason and the retirement flag identify joins; time can differ by a
second because retirement is recorded before the decision row. Turn alone is
not unique: zero-energy decisions and restart prefixes share turns. Physical
gzip line numbers below are reproducible pins. Several backups overlap; they
must not be counted as additional events.

| ID | Retirement time (+0900) / turn | Selected backup decision row; sequence | Original key / reason | Producer; tenure; burst count; forgiven |
| --- | --- | --- | --- | --- |
| R1 | 10-11 10:16:13 / 16124506 | H `bot-decisions.jsonl.31c6cc1b1895.gz`:4180; 4 | `5` / `shop:travel:await-entry` | store-router; 1; 1; yes |
| R2 | 10-11 10:17:36 / 16125597 | H `.31c6cc1b1895.gz`:4208; 32 | `9` / `home:await-fresh-knowledge` | home-visit; 2; 1; yes |
| R3 | 10-11 11:12:10 / 16227915 | H `.77e4ab80164b.gz`:5294; 13054 | `3` / `equipment-transaction:acquire-home-catalog` | equipment-txn; 9; 1; yes |
| R4 | 10-11 12:24:24 / 16394828 | H `.ba369f140f50.gz`:2485; 33454 | `ESC` + `` `n(. `` / `shop:travel` | store-router; 1; 1; yes; **unclassified; unchanged in D until separately pinned** |
| R5 | 10-11 12:47:15 / 16442332 | H `.ba369f140f50.gz`:8350; 39318 (decision time 12:47:16) | `5` / `equipment-transaction:travel-home:await-entry` | equipment-txn; 3; 1; yes |
| R6 | 10-11 12:47:20 / 16442343 | H `.ba369f140f50.gz`:8353; 39321 | `ESC` / `equipment-transaction:leave-home-for-equip` | equipment-txn; 3; 2; yes |
| R7 | 10-11 12:47:24 / 16442358 | H `.ba369f140f50.gz`:8356; 39324 | `5` / `equipment-transaction:travel-home:await-entry` | equipment-txn; 3; 3; **no** |
| R8 | 10-11 12:48:24 / 16442387 | H `.ba369f140f50.gz`:8367; 9 after restart | `9` / `shop:approach` | store-router; 1; 1; yes |
| R9 | 10-11 13:10:46 / 16500120 | H `.d1fbcc7a6040.gz`:3585; 6737 | `9` / `town:cross-town-shopping:travel-1` | cross-town; 3; 1; yes |
| R10 | 10-11 13:56:16 / 16594874 | H `.3c2bdf7818df.gz`:3361; 18501 (decision time 13:56:17) | `ESC` + `` `n&. `` / `town-progress-invariant:defect:shop:approach=>town-progress-invariant:approach` | detectors; 2; 1; yes |
| R11 | 10-11 15:10:33 / 16732099 | H `.44bd959fb3cd.gz`:8038; 35000 | `1` / `town:cross-town-shopping:travel-1` | cross-town; 1; 1; yes |
| R12 | 10-11 15:12:45 / 16732715 | H `.44bd959fb3cd.gz`:8097; 35059 | `1` / `fixedquest:q2-teleport` | quest-request; 1; 1; yes |
| R13 | 10-12 22:10:42 / 501929 | L `.3f239572048a.gz`:9902; 9762 | `ESC` + `` `n(. `` / `equipment-transaction:travel-home` | equipment-txn; 1; 1; yes |
| R14 | 10-12 22:18:24 / 503910 | L `.3f239572048a.gz`:10101; 9961 | `wl` / `equipment-transaction:equip` | equipment-txn; 1; 1; yes; **unchanged - retirement correct - handled by A** |
| R15 | 10-12 22:42:29 / 508919 | L `.d2e9d08b57c7.gz`:249; 10523 | `wl` / `equipment-transaction:equip` | equipment-txn; 1; 2; yes; **unchanged - retirement correct - handled by A** |
| R16 | 10-12 23:12:40 / 515167 | L `.d2e9d08b57c7.gz`:953; 11227 | `wl` / `equipment-transaction:equip` | equipment-txn; 1; 3; **no**; **unchanged - retirement correct - handled by A** |

The abbreviated filenames in the table all begin `bot-decisions.jsonl`.
R7/R16's decision rows contain the driver's replacement burst reason/key,
whereas the retirement list preserves the original proposal. Expected changes
must therefore assert both the producer proposal and the driver result.

### What the current two counters actually do

1. `policy.py:2939` probes the arbiter without charging; `:2983-2995` can
   reject/retire an already recurrent proposal before final accounting;
   `:3064-3071` does the same for a held claim. `:3089-3107` is final mutating
   accounting. A fix only in the CLI cannot undo this already-published event.
2. `policy_town.py:115` builds a per-family vector. It deliberately zeros
   position, turn, sequence and gold in the durable core. Equipment gets a
   distance only for the exact `equipment-transaction:approach-home` alias
   (`:166-175`), excluding the logged catalogue and travel aliases. Cross-town
   shopping is absent from the special inn-route aliases at `:296-339`.
   Q2 **already** registers BFS inn distance (`:229-252`); it is not another
   missing-Q2-alias incident. Ordinary shop distances use the legacy
   Chebyshev + Manhattan pair at `:411-437`, not an observed route minimum.
3. `town_arbiter.py:531-548` counts a repeated `(owner, vector)` after another
   pair intervenes. The detectors limit is 2, independent of a family's own
   budget. `:584-599` sets remaining to 0 and retires on that recurrence.
   Thus tenure 1/3 and estimate 0 do **not** mean eight consecutive stalled
   travel commands, or 300 stalled Home commands. Survival returns early and
   freezes errand state
   (`:486-504`), leaving `_last_pair` alone. The `melee` row is misc
   (`town_arbiter.py:177`; H :8096 / L :9901), splits the pair and can
   expose the recurrent route on resumption.
   `may_select` (`:632-664`) checks recurrence before changed retirement keys.
4. `cli.py:449-517` settles only existing store effects and admitted execution
   `done` evidence, plus observed legal route minima. It does not activate all
   business observers. It resets the **burst count**, not arbiter recurrence.
   Current route lookup follows the current claim/selected reason, so it also
   misses a previous route's arrival when the next decision has another goal.
5. `cli.py:527-570` consumes pending retirements even under a rewritten reason.
   `:547` exempts only all-misc periodic/dump retirements (`:443-446`). None of
   these 16 qualifies. A periodic save immediately before `equip` is not a
   bookkeeping retirement. `:552-556` may replace a forgiven in-store command
   with ESC; otherwise the original key can still be sent. Forgiveness at
   `:591-592` calls `town_arbiter.py:364-378`, clearing the arbiter's counters.
   It must not clear finite work obligations or the independent burst ledger.

## Group diagnosis and smallest change

Path A below means the final arbiter path
`policy.py:3089 -> town_arbiter.py:531,584,598 -> retire(:404) -> cli.py:527,547,552`.
Path B is preselection recurrence rejection
`policy.py:2983` or held-claim `:3064 -> town_arbiter.py:632-652 -> policy.py:2994`
or `:3069 -> cli.py:527`. The logged telemetry conclusively records retirement,
but does not log which of A/B first published it or the full recurrence key.
These are exact reachable source paths, not a claim that telemetry distinguishes
them. Diagnostic slice D0 below makes that distinction observable.

| Group / rows (disjoint) | Producer and retirement path | Waiting for / real observed progress | Evidence and why no credit | Smallest change / bound against alternation |
| --- | --- | --- | --- | --- |
| G1 Home entry bootstrap (R1; 1) | `_shopping_approach_key`, `policy_shop.py:5669,5768-5783`; A/B; driver path above | Correct Home page, then complete catalogue answering the pending need. Entry is one transport child, not a purchase or catalogue result. | seq 1 enters Home; seq 2 exits an incomplete page; save at seq 3; seq 4 offers entry again; seq 5 is inside Home and requests `~9`; seq 6 has current complete knowledge. Entry/exit returns the route to rank 0 and recreates its vector; recurrence is exhausted. This is a productive bootstrap with missing finite phase accounting, **not** eight failed entries. | Carry one catalogue bootstrap obligation through leave/request/adoption instead of opening another route every time. Credit one observed entry only if still an unconsumed child; use existing outside `~9` after the necessary leave, without a second entry. A complete Home page can supply catalogue content too, but is unnecessary solely to request it. One request per unresolved catalogue revision; existing request-loss bound; entry at most 8 own unsuccessful decisions. Never let repeated page open/close reset the business work. |
| G2 Home stale-address take prerequisite (R2; 1) | `_atomic_home_withdraw_dispatch_key`, `policy_home.py:2701,2738-2747`, called from `policy_shop.py:5712`; A/B | Fresh catalogue/address evidence for the **named pending withdrawal**, followed by actual pack gain matched to Home take. | seq 29 requests knowledge; 30 shows current knowledge; 31 `home:leave-for-pending-withdraw` invalidates it; 32 labels a movement `9` as await, with no execution; 33 requests again, 34 current again. Forgiveness did not end the loop: seq 35 repeats seq 31. It ends at seq 36 (`.31c6cc1b1895.gz`:4212, turn 16125615), `5ph\x1b / home:atomic-withdraw`; seq 37 at :4213 shows pack 17->18 and onward shop travel. That observed take, not forgiveness or repeated scans, ends the back-and-forth. The specific internal condition enabling it is not proved by the decision suffix. It is self-invalidating orchestration, not proof that Home stock is absent. The recurrent false/true/false states are not distinct knowledge gains. | On stale knowledge, resolve that prerequisite once through the existing Home scan protocol before offering another take route. Return its actual declared request/await, do not leave an old refusal reason on fallback movement. Separate invalid page-relative addresses from proved content; invalidate only on witnessed mutation or contrary shelf facts. One scan per content revision, bounded request settlement, 8 no-effect take decisions; if address cannot be established, record once and use the existing mandatory/optional outcome. Never close the entire Home for an address failure. |
| G3 Equipment/catalogue locomotion (R3,R13; 2) | `policy.py:11348-11388` catalogue wrapper and entrance wrapper `:7810-7854`; `_equipment_transaction_town_key`, `policy_equipment.py:2552,2649`; `_shopping_approach_key`; A/B | Observed legal BFS remaining edges decreasing to the fixed Home goal, once entry, then fresh catalogue or confirmed take. | R3 walks `(32,96)->(31,97)->(30,98)->(31,99)->(32,100)` with fixed catalogue work; vector lacks distance under that alias, consuming 8 no-progress units. R13 follows a town combat interruption; next row reaches Home `(45,123)` and offers `pd1\r`, then pack 13->14. Its `travel-home` alias also lacks distance, so an old vector can recur on resumption. Exact historical BFS minima are not in decision rows; coordinate movement alone is not proof. | For R3, request the catalogue with existing outside `~9` and stop walking: catalogue-only work needs no Home page. For R13 and other physical take/deposit legs, register the declared Home transport child for native/transaction route aliases independently of the final Observe reason. Settle prior route before selecting another command, including after misc/melee displacement. Use the qualified external-interruption re-baseline below; otherwise returning to an old minimum earns nothing. Keep 8 own unsuccessful travel decisions; no exemption for all equipment work. |
| G4 Outside equip hijacked by catalogue/router (R5,R6,R7,R8; 4) | `policy.py:7810-7854` and `:11348-11388` catalogue predicates; `policy_equipment.py:2084,2095-2105,2552`; R8 `_shopping_approach_step`, `policy_shop.py:5333`; A/B | Existing outside-home equip action, exact `sub_hand` target confirmation; exit once to permit that action. | At seq 39317 onward the session requires `outside_home`, target `pack:496a911c336315db:0`, slot `sub_hand`; knowledge is invalidated. Catalogue entry wins outside; Home owner sends `leave-home-for-equip`; no `equip` between 39317 and 39324, pack 20 unchanged. R8 is the same scene after restart, now a router step-off/return with ready knowledge and outside session. Arbiter correctly detects repeated context states. No business progress was possible **under this offered sequence**, although the pack equip is feasible. | Do not offer catalogue/plan Home routing while an admitted session's next action requires outside context. Continue that same session after its one witnessed exit; use its transaction result, not a new priority rung. Check both catalogue predicates and plan projection/router, so R8 cannot be an alias escape. No new owner or reordering of owners. One exit obligation per existing action, 8 action-confirmation decisions; if equip fails, existing current-loadout closure + record. No further Home entry until a remaining action actually requires Home. |
| G5 Cross-town shopping walk (R9,R11; 2) | `_cross_town_shopping_key`, `policy_shop.py:1721,1820-1832` -> `_town_teleport_key`, `policy_town.py:6484-6588`; A/B | Inn BFS minimum for the selected town leg, then observed destination town. Purchases reduce actual carried shortage separately. | R9 moves toward `(37,119)`; R11 resumes after monster pursuit/loot from `(22,110)`. Exact `town:cross-town-shopping:travel-1` is missing from the inn-distance branch. Some vectors change due to other durable facts, explaining mixed `progress=true`; repeated durable vectors retire even on a moving leg. This is a missing route signal, not proof of exhausted towns. | Bind shopping to the existing declared inn route, not an old supplier goal. Same settlement/minimum rule as G3. 8 own non-progress travel decisions; candidate towns tried once in the existing expedition; keep its tried set across legs. Price/pack/stock failure still uses existing results. Travel does not itself satisfy the carried shortage. |
| G6 Detector replacement supplier route (R10; 1) | `_town_procurement_decision`, `policy_town.py:1293,1600-1637` -> `_shopping_approach_key`; A/B for detectors | Actual BFS travel to bound supplier; exact identify-staff acquisition. A marker or route substitution is not progress. | seq 18497 detector route to Magic; 18498 leave wanted staff shelf; 18499 to Alchemist; 18500 leave wanted star-identify shelf; 18501 detector route back to Magic; 18502 `pm1\r\r`; 18503 pack 16->17 and purchase message for 19-charge staff. Detector vector has no route distance, and new stock evidence is not a target-scoped receipt. However two shelf exits before composition are also a real scheduling defect. The later buy cannot retroactively justify either earlier diversion. | Preserve the already selected composable shelf operation through its one cleanup exit and outside composition. Refuse a detector substitution to a competing supplier while that operation is unresolved; if it is uncomposable, record its concrete refusal once, release it by existing rules, then choose the next existing errand. No blanket detector forgiveness. Credit only matched acquisition/new target evidence, once. Route child 8, detector unresolved routing 2, buy confirmation 8; pending executor tails retain their existing bound. Genuine ownership/contract violations still stop visibly. |
| G7 Q2 route resumption (R12; 1) | `_fixed_quest_key`, `policy_quest.py:3987` -> `_town_teleport_key`, `policy_town.py:6484`; vector `:229-252`; A/B | Inn BFS new minimum on resumed Q2 travel, then observed requested town. | Before interruption seq 35042 is `(23,51)`; pursuit takes character to `(21,65)`; seq 35059 resumes toward `(28,56)`, next `(22,64)->(22,63)->(22,62)`. BFS distance is already registered. The misc/melee row at :8096 splits the pair (survival itself leaves `_last_pair` alone); a previously visited vector can then recur, and `may_select` rejects it at recurrence 2 before another travel attempt. This is **not** lack of a Q2 distance branch; nor does the suffix prove a new minimum on every pursuit step. | Retain the admitted Q2 route identity through interruptions. After witnessed displacement by another owner (including misc/melee), re-baseline at the resumption position; this external-cause baseline earns no credit and does not reset the unsuccessful-own-decision count. The next observed decrease below that resumption baseline earns route credit, even above the pre-pursuit minimum. Charge unsuccessful **own** decisions against Q2's existing 3, bypassing stale pair recurrence only for this qualified route at preview and final accounting. Survival without displacement only freezes; it never resets the minimum/counter. A real repeated route still retires within 3 unsuccessful own decisions, with visible failure; do not skip Q2 as optional shopping. |
| G8 Light equip alternation (R14,R15,R16; 3) | Existing equipment dispatch versus survival `restore-lantern`; A/B | Physical swaps alternate, with no net completed work. | Existing retirement is correct; save/dump is not the cause. The 23:12:48 state capture below confirms the light-slot context. | **Unchanged - retirement correct - handled by A**, step 3 A branch `light-swap-1013` (`f52ce85b`, `policy.py:12840-12850` there). A suppresses `_empty_lantern_to_restore` while usable light is worn. D changes no light selection/settlement rule. D6 adds one regression control after A lands. |

Counts: 1+1+2+4+2+1+1+3 = **15 classified**, plus **R4 unclassified = 16**. G3/G5 are missing-signal
accounting defects; G7 is accounting of resumed work. G1 combines a missing
finite prerequisite receipt with redundant entry. G2/G4/G6 contain actual
producer sequencing defects: crediting UI oscillation would hide them. G8 is
real repetition with a justified retirement. Do not classify all 16 as false
positives, and do not classify all moving keys as productive.

### Limits of causal proof

The rows establish reasons, transitions, selected targets and reported pack
counts; pack counts/payment are proxies until matched to item state. A posted
take/buy is not a receipt. The full physical before/after item facts and BFS
minima must be pinned during implementation from matching state/response
records. `H/bot-state-fixed.jsonl.live-1620.gz` covers turns
16844673-16853798, after every CL45 incident (last 16732715); it supports
none of R1-R12. Actual usable captures are under
`C:\hengband\bot-client\jsonlog\` (abbreviated J):

* C1 = `autorecover-20261011-124735-town-blocked-owner-retired-burst`.
  `.bot-decisions.jsonl.gz`:158/161/164 match R5/R6/R7; its
  `.bot-state-fixed.jsonl.gz`:63-65 (16442332), 66-68 (16442343),
  72 (16442358) show pack 20, carried slot p tval36/sval11,
  and absent worn sub_hand. Store rows 65/68 show Home (7). These are physical context pins, not
  a claim that an action posted in those rows succeeded.
* C2 = `autorecover-20261012-231248-town-blocked-owner-retired-burst`.
  `.bot-decisions.jsonl.gz`:88-90 show save/dump/R16 at 515167;
  `.bot-state-fixed.jsonl.gz`:92-95 show pack 14, carried slot l
  tval39/sval0 and worn light tval39/sval1. Keep raw encoding and
  fuel fields in the future fixture; these observations alone do not
  reconstruct R14/R15's earlier fuel values.

Use C1 for D1 and C2 for the single D6 test. Turn is not a response boundary:
extract posted-character/response ordering and hashes in implementation,
and stop replay at the first changed command. Other missing state pins must
be labelled constructed, not described as historical full-state replays.
Do not invent low-level fuel or topology evidence. The measurement versions
are 27f32cbb for CL45 and 32f93f9c for low III; use current-base replay to detect
which older symptoms are already corrected. Missing latched state means
reconstructed baselines earn no credit.

## Shared accounting rule, without a new scheduler

Use one settlement receipt at the existing decision boundary, before both
`preview_may_select` and final `observe`; the CLI consumes the same evidence
for its burst ledger. This is required because crediting only the burst cannot
prevent a false single retirement. Keep receipt generation read-only during
preview; consume each observation once during final settlement, by decision
identity, including zero-energy decisions.

The receipt belongs to an existing admitted execution and its finite child:
visit epoch, producer, stable operation/action identity, target, expected
effect, source observation/request identity, previous facts, observed facts,
and route minimum when applicable. A work ID ending in decision sequence is
provenance, not a fresh business objective. Deduplicate equivalent aliases by
operation reference and target, not by reason or claim ID. Keep the outstanding
previous operation until it is settled even if the next chosen claim is a dump,
safety action, catalogue scan or shop leave. Prior observation settlement does
not authorize a different owner's key.

For transport, bind the goal chosen by the actual producer to its admission.
Use `_town_map_goal_route` on observed legal topology; retain a minimum for
that fixed target and topology revision. If no path/evidence exists, do not
substitute Euclidean distance or the intended next step. Baseline, route
reissue, store exit, renamed reason and a new claim ID never renew credit.
Topology revisions require observed changed edges, not cache invalidation.
Entry/exit is an individually consumed child milestone only where that
operation actually needs it; returning to an already consumed entry cannot
reset its root. New confirmed business work can create a new finite child;
opening a StoreVisit alone cannot.

Replace vector-recurrence rejection only for the qualified child rows. Keep
legacy accounting for rows without an observer; do not disable global
recurrence in one patch. Qualified route failures use existing family bounds
(router/transaction/cross-town 8, Q2 3, detector routing 2) against their own
decisions without new minimum/effect. A stalled command is charged once;
executor polls with a posted finite tail freeze policy accounting under the
tail's own bound. A selected no-step without a posted tail is still charged.
Safety/bookkeeping freeze the interrupted errand; external displacement follows
the qualified re-baseline rule below, never a counter reset. Genuine
contract failures retain their current visible stop regardless of optionality.

An interruption by another owner that **observably moves** the player
re-baselines the retained route minimum at the resumption position, once per
matched interruption/resumption identity. This includes misc/melee, pursuit
and loot when attributable to that other owner, as well as survival. Require
the same admitted operation, target, and observed topology plus both position
observations. Re-baselining is external-cause accounting, not productive work:
it grants no receipt, does not reset own unsuccessful decisions or the burst,
and cannot be obtained by the route's own bounce, renamed alias, same-owner
retargeting, save or stationary safety action. The next legal observed decrease
from this baseline qualifies normally at both arbiter seams and CLI. Without
that proof retain the old minimum and charge the resumed own decisions.

**No memory across an autorecover restart (2026-10-09 decision).** Every bound,
receipt-consumption set, route minimum, work outcome and counter introduced by
D is per process and per town visit. They vanish on restart; fresh observation
starts an uncredited baseline. No checkpoint serialization or surviving ledger
is proposed. Recorder replay pickles are offline evidence, not recovery state;
existing replay compatibility tests do not authorize carrying D fields into a
restarted bot. Existing process-local equipment visit closure and shop/expedition
records can serve one-time outcomes during that process/visit only. Forgiveness
must not reset these while the process continues. The outer bound is the
existing autorecover escalation (same reason three times in 30 minutes) plus
the measured town restart/stop gate (at most three per 24 active hours). R7
illustrates restart termination, not cross-restart convergence. No slice needs
restart-surviving fields and no owner question remains open.

### All kinds of work: the continuing progress contract

The 10-05 decision remains all-kind. The 10-06 table and review are retained
as the full producer inventory starting point; slices 0/1 landed, but their
shadow-v1 work tags do not certify business effects. This compact table states
what every kind must prove. Only the groups above drive the initial D slices;
remaining kinds need observation qualification before graduation, rather than
being silently exempted or immediately implementing all old slices 2-6.

| Work kinds / shared children | Qualifying observation; no-credit case | Bound / completion |
| --- | --- | --- |
| Buy: survival supply, mining kit, quest carry, ordinary and optional stock | Named carried quantity/usable charges acquired, matched transaction; payment alone, expected selection or released tail is no credit | Existing buy bound 8; requirement/finite target reached; absent/unaffordable/uncomposable offer ends by existing mandatory/optional policy |
| Sell, Home disposal sale, sale inscription/address | Exact surplus quantity removed with sale evidence; inscription/address preparation once per named item; slot relabel alone earns nothing | Sale 3, address 3; reserved stock retained; refused item not reoffered unchanged |
| Supplier browse/shelf absence | First complete relevant shelf answers the live need at its actual revision | 8; duplicate shelf/exit/reentry is not new evidence |
| Store/Home/inn/quest approach, native travel, entry, exit | Observed BFS minimum; correct page/context child once; desired town arrival | Bounds as above; finite cleanup; no credit for intended movement or repeated rank 0 |
| Home catalogue/knowledge/page addressing | Matched complete response or complete page answers unresolved content/address obligation, including empty Home; unique missing page proved | Request-loss/settlement protocol retained; 8 stalled child decisions, not 300 unproductive refreshes; repeated identical refresh is no credit |
| Home deposit / space / weight | Named pack-to-Home quantity transferred; actual space/overload obligation improves | 8; observed full/refused deposit ends via existing relief/closure policy; speculative catalogue insert is no credit |
| Home withdrawal (identification, quest, ammo, device, equipment, restore) | Named quantity enters pack, matched take evidence, including merged stack | 8; absent/stale address/pack-full resolved once; queued take is no credit |
| Home visit/errand executors | The selected catalogue/take/deposit observation, not phase advance or executor index | Selected child's bound; unresolved operation settles before competing work |
| Home-full relief / retry / disposal / destruction / overflow | Confirmed Home take followed by safe sale/destruction frees Home space; carried destruction frees pack space only | Relief orchestration 3, take 8, sale/destroy 3; existing safe sale then cheapest unneeded destruction ladder; protected/uncertain candidates excluded; exhausted optional deposit ends, mandatory failure visible |
| Identification, full identification, device processing/absorption | Named knowledge level or usable device/status objective advances; consumed source by itself is not success | Identification 3, device 8; impossible source/result resolved once |
| Equipment search, takeoff/equip, suppression inscription, curse/enchant | Fresh validated calibration/catalogue resolves a missing input; pure comparison computation earns no game-progress credit; exact worn target/slot or requested flags/bonus confirmed; required abilities retained | Operation 8; fixed finite obligations, reverse swap/strip-restore does not regenerate debt; failure uses current-loadout rule plus record |
| Stat/experience restore, healing/food/survival, town combat | Named deficit/status improves or perceived threat is removed; survival remains an interrupt | Existing operation bounds; no safety retirement; unresolved required safety stays visibly failed |
| Quest request/report/reward/entry and Q2/Q22 travel | Observed quest status/reward/floor or declared route progress; prompt answered alone is not effect | Existing finite service/quest bounds (quest arbitration 3); unknown prompt visibly stops |
| Restock/fundraising/cross-town purpose | Fresh shelf revision, confirmed gain toward declared funds/stock, observed town; tried targets remain finite | Existing stockout/mining cap, including 3 stockout attempts; no time-based renewal of an exhausted purpose |
| Recall/departure, loot/exploration | Visible recall true plus advancing game turns within game's finite activation allowance, then arrival; carried target acquired or new relevant observed map facts | Existing recall bound and departure gates; no hidden countdown; visit exit resets visit accounting only after actual outside observation |
| Plan routing, detectors, terminal declarations, bookkeeping | Routing selects an executable named child; detector inherits selected observation; impossibility emits a one-time record; save/dump is not errand progress | Routing 3, detector 2; no repeatable terminal WAIT; bookkeeping spends/forgives no errand debt |

Weight remains a deposit/overload need, never an equipment comparison score.
Depth-band required abilities and expected damage per player turn against AC100
remain authoritative. Nothing here widens the 80F descent gate.

## Implementation slices and concrete pins

Each slice can merge alone, retains log-only and the independent burst, and
requires its focused regressions plus the repository's normal implementation
checks at that later time. No tests are run by this design task. Extract raw
fixture provenance/hashes and state-response boundaries during implementation.
Replay policy only up to the first changed command; subsequent historical
boards are observer controls, not a claim that the counterfactual game produced
them. New tests are explicitly new; existing tests listed below were found by
alias searches and direct assertion reads, not guessed from extractor filenames.

Merge order by change size is D0, D1, D2a, D3a, D2b, D3b, D4, D5;
D6 is an independent test-only control after A lands. D2/D3 are deliberately
split into producer/alias and route-settlement parts. Each can merge without
another D slice: add focused local tests in the same commit, use existing
public producers and seams, and do not rely on D0 schema to alter behavior.
D2b/D3b can carry the shared settlement helper with their own opt-in aliases;
the other slice reuses it if already present (otherwise carries the minimal
helper itself). No global accounting switch is bundled. Shared-helper overlap
requires a routine rebase, not a dependency on the other behavior fix.

The R table is the authoritative file/row/turn/original-key/reason pin for
every row reference below. ESC and native travel strings are literal as shown
there. C1/C2 denote the exact J capture stems and rows above. Every expected
proposal is checked before driver override, and every driver result is checked
for the expected absence/presence of retirement or burst.

| Slice | Pins: today's key/reason -> expected key/reason and result | Merge boundary and validation |
| --- | --- | --- |
| D0: disclose retirement trigger | All R1-R16 at their table pins: unchanged original proposal and driver result, including burst R7/R16; C1 decision :164 / C2 :90 remain `5 / town:blocked:owner-retired-burst` | Observational only. Log publishing entry point `policy.py:2994`, `:3069`, or final `:3086` retirement branch (final accounting :3089 onward), exact recurrence key/count/limit and `_last_pair` before/after, trigger category, own unsuccessful count/bound, operation/visit epoch, old/new minimum, matched effect identity, raw/final key/reason. Emit operation/visit/own-count/bound evidence on every decision, including decisions with no retirement; seam/recurrence publication details accompany retirements. Distinguish preview evidence from mutating publication and deduplicate one retirement. Existing D0 tests below extend schema only. D0 is required before measurement starts. |
| D1: outside equip continuation; G4 | R5/R8 at table rows/turns: `5 / equipment-transaction:travel-home:await-entry` and `9 / shop:approach` -> resolved pack wield + `equipment-transaction:equip`, then target sub_hand confirmation. C1 state :63-65/66-68/72 and decisions :158/:161/:164 pin R5-R7. R6 `ESC / leave-home-for-equip` becomes unnecessary after the single required exit; R7's repeated entry/burst is absent. Retain one `ESC / equipment-transaction:leave-home-for-equip` when actually inside Home. Exact wield selector derives from pack/session, not guessed item ID. | Guard both catalogue predicates and Home route projection while current session requires outside context. Do not alter Home-required phases or later owners. Pin explicit existing equip refusal -> current gear closure/record once; public-path regression must fail before/pass after. Existing full-Home closure and equip-only assertions stay green. |
| D2a: outside catalogue request; G3/R3 | R3 H `.77e4ab80164b.gz`:5294, seq13054, turn16227915: `3 / equipment-transaction:acquire-home-catalog` -> `HOME_KNOWLEDGE_MACRO` (`~9\x1b`, existing constant) / `equipment-transaction:catalogue-request-knowledge`, no Home walk or retirement. :5295, same scene `(32,100)`, already proves outside `~9 / home:request-knowledge-scan` works. | Catalogue-only wrapper adopts existing `_home_catalogue_work_key` outside request/await behavior in both acquisition branches. Home page adds no catalogue content; local page addressing belongs to later physical take/deposit. No change to actual Home-required transaction routes. Inflight request awaits existing posted scan without new movement/repost. |
| D3a: cross-town inn alias; G5 | R9/R11 table pins: retain `9`/`1 / town:cross-town-shopping:travel-1`; expected inn BFS route fact, no false missing-distance retirement for observed decreasing legal route. | Add shopping alias to existing inn envelope only. Tried-town/fare/shortage rules unchanged. This alone does not claim interruption recurrence solved; that is D3b. |
| D2b: physical Home route settlement; G3/R13 | R13 L `.3f239572048a.gz`:9902, seq9762, turn501929: retain native Home travel / `equipment-transaction:travel-home`, no old-vector refusal after misc/melee :9901. Next observed entry/take `pd1\r` and pack13->14 settles the matched child once. | Bind physical Home route and settle preceding observation before next selection at preview/final/CLI. Apply external-displacement re-baseline; baseline earns no credit. Stationary/bounce without external cause still retires within 8 own unsuccessful decisions. Independent of D2a's catalogue shortcut. |
| D3b: interrupted inn-route accounting; G5/G7 | R9/R11 retain table key/reason under shopping alias; R12 H `.44bd959fb3cd.gz`:8097, seq35059, turn16732715 retains `1 / fixedquest:q2-teleport`. Misc/melee :8096 splits the pair. At resumption `(21,65)`, re-baseline once; next legal decreases earn credit even above old minimum near `(23,51)`. Following observed `4` completes the inn leg. | Q2 already has BFS. Qualify bound inn child at preview/final/CLI independently of D3a; recognize shopping alias locally if needed. An unsuccessful resumption is charged, not immediately rejected by old recurrence; Q2 3, shopping 8 own unsuccessful decisions. No counter reset on displacement; no combat/loot credit to the route. Finite towns and mandatory outcomes remain. |
| D4: catalogue/take sequencing; G1/G2 | R1 H `.31c6cc1b1895.gz`:4180, seq4, turn16124506: redundant `5 / shop:travel:await-entry` -> outside `HOME_KNOWLEDGE_MACRO / home:request-knowledge-scan` (home-scan holder), followed by correlated adoption. R2 :4208, seq32, turn16125597: `9 / home:await-fresh-knowledge` -> same explicit home-scan request; awaiting a posted request uses `home:scan-await-observation`, never fallback movement. Named pending withdrawal then uses `home:atomic-withdraw` with fresh local address. | Retain first actually needed physical entry; catalogue-only bootstrap may scan outside directly. Preserve proved content across cleanup; invalidate local addresses after mutation and reacquire safely. No request repost while inflight, no unsafe address reuse, finite loss/settlement bounds. Existing home-errand holder uses its own request/await declaration; do not steal it to home-scan. New G1/G2 tests pin exact holder. |
| D5: bound Magic shelf continuation; G6 only | R10 H `.3c2bdf7818df.gz`:3361, seq18501, turn16594874: detector replacement `ESC + native Magic travel / town-progress-invariant:defect:shop:approach=>town-progress-invariant:approach` -> continuation of the already bound Magic staff shelf operation, no second supplier route. At the recorded Alchemist exterior `(37,91)`, expected key is the existing `` ESC + `n&. `` macro with reason `shop:travel`, attached to the retained Magic shelf operation's transport continuation; it must not create another operation/route identity or select an Alchemist leg. Immediate Magic buy bytes are not legal at that position. At the matched Magic page, its existing `shop:in-store-buy` or outside `shop:one-shot-buy` composer continues the same operation. :3362's later `pm1\r\r` is an observer control, not a counterfactual board. | Preserve named operation across its necessary cleanup/composition; no competing Alchemist route before settlement. Buy receipt must match target, no pack-count-only credit. Uncomposable operation retains its existing concrete refusal control, not a 'depends' acceptance criterion for this pin. Existing genuine contract defects still stop. No R4 behavior or generic new business-receipt framework bundled. |
| D6: one regression control after A lands | C2 state :92-95, turn515167, decision :90 / R16 L `.d2e9d08b57c7.gz`:953: historical `wl / equipment-transaction:equip` -> driver `5 / town:blocked:owner-retired-burst` remains a historical fact. With A present, this usable worn-light board must not offer `restore-lantern` from `_empty_lantern_to_restore`; next overall key/reason follows other needs and is not forced to depart. | **One new test only**, exercising the C2 board with A's public light-selection path. No D light rules, no D changes to R14-R16. Existing light tests remain controls; historical snapshots/assertions unchanged. A qualification is separate; D's other slices/measurement need not wait for A. |

**R4: unclassified until pinned; excluded from D's behavior changes.**
Keep its current retirement and key/reason in the R table. The appropriate
decision evidence is H `.ba369f140f50.gz`:2473-2489: weight deposit
pack19->14 at seq33451, Alchemist leave, Home return, `~9`,
`identify-staff-reserve-unavailable`, and equip `wjy`. Those decisions do not
prove the unresolved Home obligation or an exact deposit receipt. No
conditional-outcome slice is dispatchable. A future separate design must
supply matched state, a named obligation, and one expected key/reason before
including R4; this revision deliberately selects the review's exclusion option.
R4's expected D outcome is unchanged `ESC + native Home travel / shop:travel`
and existing retirement, pending that classification. It blocks final all-kind
enforcement qualification until resolved, but does not block any D slice's
independent merge or diagnostic measurement clock.

### Existing tests: what flips and what must stay green

The current tests mostly encode contracts already intended, not the newly
recorded failures. There is **no honest list of existing tests that are known
to fail on this checkout** without running them; no run is authorized here.
Do not weaken good expectations just to make changed stop timing pass.

| Slice | Existing module and exact test; intended effect on expectations |
| --- | --- |
| D1 | `tests/test_policy_equipment.py::test_blocked_home_does_not_steal_outside_home_transaction`; add invalidated catalogue + public path, new control would fail before/pass after; existing helper expectation stays. `::test_outstanding_equipment_work_always_projects_a_home_need` stays green: its fixture is a Home deposit. A new outside-equip variant flips `equipment_work_need_present` true -> false while retaining `outstanding_equipment_work` true. `tests/test_equipment_transaction_session.py::test_equip_requires_outside_home_and_target_slot_confirmation` and `::test_home_physical_context_keeps_equip_phase_inside` stay unchanged. |
| D2b | `tests/test_town_arbiter.py::test_a2_every_town_approach_with_falling_claimed_distance_keeps_progress`: extend physical Home travel aliases; catalogue-only requests use D2a instead; added cases flip false retirement to no retirement. `::test_nonconverging_store_walk_retires_within_recurrence_budget` stays green: it directly observes unqualified `shop:approach`; retain `assertLessEqual(retired_at, limit * 2 + 1)`. New qualified Home-route controls instead pin retirement within 8 unsuccessful own decisions; do not generalize their exemption to this shop test. `::test_equipment_home_equidistant_oscillation_retires_at_stall_budget` remains a negative control. |
| D3a/D3b | `tests/test_q2travel_progress_recorded.py::test_walk_to_the_inn_is_progress_and_continues`, `::test_constructed_q2_teleport_walk_is_progress`, `::test_constructed_q2_teleport_walk_that_does_not_close_still_retires` stay green; add pursuit/resumption pin that flips immediate retirement to continued bounded walk. `tests/test_policy_town.py::test_cross_town_tries_each_visited_town_once_then_visible_stop_remains` and `::test_cross_town_expedition_never_weakens_recall_entry_invariant` remain unchanged. `tests/test_owner_retirement_slice1.py::test_survival_interrupt_freezes_errand_budget_and_returns` remains a freeze control. |
| D4 | `tests/test_home_knowledge_scan.py::test_no_rerequest_while_request_is_unsettled`, `::test_unposted_or_replaced_request_does_not_consume_latch`, `::test_pin_a2_exit_and_reentry_reject_prior_visit_response` stay unchanged; `tests/test_home_catalogue_response_in_store.py::test_recorded_response_is_adopted_without_reposting_home_scan` stays green and supplies the in-Home completion control. `tests/test_policy_home.py::test_pending_withdraw_hold_is_legitimate_town_progress` gains stale-address variant whose added assertion flips. `tests/test_policy_shop.py::test_store_exit_snapshot_still_steps_off_for_reentry` remains valid for genuinely needed reentry, not permission to repeat catalogue debt. |
| D5 | `tests/test_policy_shop.py::test_observed_uncomposable_nonhome_stop_advances_without_entry`, `::test_uncomposable_home_stop_advances_without_entry` remain failure controls. `tests/test_owner_retirement_slice1.py::test_observed_store_effect_resets_but_admission_and_ui_changes_do_not` gains catalogue/target-operation receipt variants; new matched-effect assertions flip, UI/admission assertions stay. `::test_admitted_route_new_minimum_resets_but_bounce_and_new_target_do_not` remains unchanged; D2b/D3b add externally displaced re-baseline controls, keeping self-bounce and new-target no-credit assertions. |
| D6 | Existing `test_newchar_light_loop_recorded.py::test_worn_torch_fuel_rule_cannot_flip_on_next_turn`, `test_newchar_light_churn_recorded.py::test_restored_checkpoint_retires_torch_debt_after_confirmed_lantern`, `::test_revert_proof_recreates_live_restore_command`, and `test_home_light_alternation.py::test_tail_property_rejects_an_own_alternation` keep current assertions. Single new C2 control changes pre-A restore offer present -> absent after A; D6 flips no existing light assertion. |
| Every slice | `tests/test_owner_retirement_slice1.py::test_two_continue_third_stops_even_with_reason_rewrites_and_forgiveness`, `::test_bookkeeping_retirements_never_count_toward_the_burst`, `::test_hidden_retirement_does_not_swallow_a_typed_contract_stop`, `::test_off_hidden_retirement_has_a_visible_stop` retain their expectations. Changes to progress coverage do not abolish intentional failure handling. |

### Alias inventory: explicit assertion disposition by slice

Read/search only, not an execution result. The review's command restricted to
`tests/test_*.py` currently finds **24 modules** (the review reported 20);
fixture JSON hits are provenance rather than test modules. The inventory below
includes all 24, including the ten omissions named by the review. A green
module means its existing affected assertions are preserved unless a flip is
explicitly listed; unrelated assertions stay green in every slice. Added
regressions fail before/pass after, but that is not an existing assertion flip.
Do not continue a historical sequential replay past a changed key: split its
later page/response checks into independently attached controls.

| Slice(s) | Existing module/test: stays green versus flips (specific assertion) |
| --- | --- |
| D0 | `test_owner_retirement_slice1.py::test_hidden_c_and_a_are_logged_and_forgiven_with_original_reason` and `test_cli.py::test_decision_record_carries_home_gate_evidence`: retain original reason/key/forgiveness and Home evidence; extend diagnostic schema for seam/recurrence/visit/counters. No behavioral assertion flips. |
| D1/D2b | `test_equipment_homefull_step15a.py`: `test_pin4_rearm_forgiveness_and_relief_preserve_tombstone` preserves visit closure under forgiveness; `test_pin6_restart_full_page_refires_without_refusal` preserves fresh-process behavior; `test_pin7_equip_only_still_executes_and_withdrawn_item_stays` preserves equip-only execution and owned pack item; `test_eqtxn_reserved_capture_pins_close_unexecutable_home_work_once` retains scene_b `equipment-transaction:travel-home` for physical work. No flips. Its existing 50ecc1eb closure is reused within process, never extended across restart. |
| D2b | `test_travel_interrupted_store_await.py`: `test_recorded_equipment_home_travel_owner_replans_interruption` retains nonempty native macro and `equipment-transaction:travel-home`; `test_genuine_entry_waits_once_without_duplicate_post` retains no duplicate post. No flips; new misc displacement tests change accounting, not transport acknowledgement semantics. |
| D3a/D3b/D5 | `test_crosstown_alt_recorded.py`: `test_cross_town_declared_reach_overrides_stale_store_goal` retains declared inn goal; `test_after_refusal_travel_reaches_recorded_target_without_reentry` retains convergence/no Home reentry; `test_no_operation_settles_observed_shelf_even_after_plan_advanced` retains genuine uncomposable-refusal settlement. No flips; historical cycle facts remain frozen. |
| D1/D2b | `test_home_route_release_recorded.py`: `test_failed_deposit_observes_before_equipment_and_hands_off_once` retains physical `equipment-transaction:travel-home` only after observed failed deposit; `test_observed_delta_closes_before_bookkeeping`, `test_unreleased_or_same_turn_board_cannot_confirm_or_charge` retain matching/charging barriers. No flips. |
| D4 | `test_home_withdraw_moved_address.py`: `test_pending_take_with_owners_on_both_sides_rescans_then_takes_later` and `test_batch_owner_beyond_the_prefix_rescans_instead_of_failing` flip `(decision,reason) == ('5','shop:travel:await-entry')` to explicit surface-appropriate scan request `HOME_KNOWLEDGE_MACRO / home:request-knowledge-scan` after stale address; keep batch retention, nothing-failed, and fresh resolved page/letter/take assertions on independently attached response. `test_errand_target_beyond_the_prefix_rescans_instead_of_failing` flips helper no-step/old `await-fresh-knowledge` to the owning home-errand's actual request/await; retain fresh target and selecting_branch `home-errand`. `test_owner_absent_from_the_fresh_catalogue_is_still_unobserved` retains actual absent-target/deferred-site outcome. |
| D2a | `test_live23_home_cycle.py`: `test_recorded_entry_completes_catalogue_before_other_errand` flips initial `choose_key(boards[0]) == '5'` and `travel-home:await-entry` to `HOME_KNOWLEDGE_MACRO / equipment-transaction:catalogue-request-knowledge` for catalogue-only work. Keep fixture hash/data assertions; detach subsequent historical page and its catalogue-adoption/closure assertions. The same initial `'5'` assertions flip in `test_historical_competing_actor_names_registered_holder_in_shadow` and `test_registered_catalogue_keeps_turn_even_for_later_mining_withdraw`; retain independently attached holder/defer/violation assertions. `test_recorded_off_scan_continues_registered_catalogue` flips historical key/reason equality at the first catalogue-only outside acquisition; preserve earlier prefix, detach later response controls. `test_recorded_partial_home_page_requests_catalogue_in_place` and `test_restored_legacy_entry_declaration_still_requires_catalogue_evidence` retain scan/holder controls. |
| D1/D2a/D2b | `test_equipment_home_full_incident_recorded.py`: `test_confirmation_stall_does_not_reapproach_a_blocked_home` and `test_full_home_ends_transaction_deposit_with_visible_reason` retain no-reapproach/current-loadout closure and no equipment-owner restart of closed optional work. No flips. |
| D2a/D2b/D3a/D3b/D4 | `test_ownership_s2a1_closure.py`: `test_the_rev92_rows_have_the_design_kind` retains `acquire-home-catalog -> Reach` typing for the legacy reason; D2a emits the existing request alias instead of repurposing a Reach reason. `test_every_reach_reason_site_writes_its_slot`, `test_the_teleport_walk_itself_is_adopted`, `test_a_restored_checkpoint_carries_no_capture` retain goal provenance/inn goal/replay compatibility. No flips. |
| D1/D2a/D2b/D3b/D4 | `test_ownership_s3a_record.py`: `test_transaction_entry_wait_keeps_its_separate_observation`, `test_incomplete_page_and_entry_wait_keep_observe_identity`, `test_non_operation_home_reasons_have_explicit_types`, `test_store_entry_wait_completes_on_target_page`, `test_home_scan_completes_on_catalogue_adoption` retain existing typing and declared child completion. Synthetic old aliases remain valid controls; producer replacement is not a registry remap. `test_old_checkpoint_defaults_for_new_record_fields` remains replay-only compatibility. No existing flips; new public alias/holder tests cover requests. |
| D1/D2b/D3b | `test_s33_batch_context.py`: `test_recorded_outside_action_is_not_a_home_need`, `test_outside_takeoff_runs_through_choose_key`, `test_survival_resumes_the_same_posted_equipment_route`, `test_home_route_completes_on_observed_arrival` retain outside classification, key, claim/budget_ref, and arrival closure. Stationary survival does not trigger displacement re-baseline. No flips. |
| D2b | `test_calibration_crlf_dump_recorded.py::test_town_optimizer_plans_the_home_resist_confusion_ring`: retain calibrated target/flags and physical Home travel tuple. No flips; work is a ring take, not catalogue-only. |
| D2a | `test_catcycle.py::test_partial_home_requests_catalogue_before_other_errands` flips first current `choose_key(boards[0]) == recorded key` at catalogue-only acquisition to `HOME_KNOWLEDGE_MACRO / equipment-transaction:catalogue-request-knowledge`; detach later page controls. `test_frozen_recorded_cycle_and_posted_actions` preserves recorded ESC/entry facts. `test_in_home_catalogue_reply_adopts_before_next_home_work`, `test_posted_scan_waits_for_reply_without_reissuing` retain matched reply/no-repost assertions. |
| D3a/D3b | `test_goldburn_shopping_constructed.py`: `test_fare_does_not_change_durable_progress_or_retirement_key` retains fare no-credit; `test_alternating_spenders_retire_and_spending_cannot_clear_retirement` retains both retired owners, unchanged retirement keys (stationary spends cannot re-baseline); `test_arrival_completes_transport_claim_before_shop_entry` retains arrival settlement. No flips. |
| D4 | `test_home_catalogue_response_in_store.py::test_recorded_response_is_adopted_without_reposting_home_scan` retains adoption/no repost. No flips; in-Home control remains available even when earlier catalogue-only travel is removed. |
| D6 | `test_home_light_alternation.py::test_tail_property_rejects_an_own_alternation` retains own-alternation rejection. No D change; A-specific changes belong to A. |
| D4/D5 | `test_input_executor.py::test_recorded_prompt_history_receipt_releases_only_matching_post` retains matching post/terminal `home:scan-incomplete-open-page`; `test_p2_inside_home_knowledge_continuations_remain_exact` retains knowledge bytes/tail ownership. No flips; posted prompts are not business progress. |
| D1/D2b | `test_item_reservation.py::test_consumption_cannot_borrow_a_stale_transaction_owner_reason`, `test_on_predicate_exception_filters_then_emission_stops`, `test_need_query_skips_foreign_items_without_poisoning_owner_handoff` retain reservation/producer identity and typed defect stop. No flips. |
| D4 | `test_live35_store_page.py::test_recorded_home_scan_exit_survives_production_arbitration` retains ESC/reason for a genuinely incomplete rendered page; `test_store_language_is_preserved_for_all_exit_and_wait_owners` retains language. No flips; no repeated entry to get catalogue follows that exit. |
| D2b | `test_margin_ratio_tour_divergence_recorded.py::test_first_divergence_is_the_home_trip_for_the_nodachi` retains physical take tuple `ESC + native Home travel / equipment-transaction:travel-home`; prefix assertions stay green. No flips. |
| D4 | `test_policy_home.py::test_pending_withdraw_hold_is_legitimate_town_progress` retains pending posted take hold/no defect; `test_home_entrance_control_without_pending_is_unchanged` retains entrance wait when there is no named catalogue/take debt. No existing flips; stale-address new variant emits request instead of movement. |
| D3a/D3b | `test_policy_town.py::test_cross_town_tries_each_visited_town_once_then_visible_stop_remains` and `test_cross_town_expedition_never_weakens_recall_entry_invariant` retain finite candidate and recall gating. No flips; add alias-route facts and interruption controls. |
| D2a/D4/D5 | `test_town_cure_supplier_recorded.py::test_walled_prefix_reproduces_live_except_declared_boards` retains `_live(15) == ('5','equipment-transaction:travel-home:await-entry')` as historical fact and current `prefix[15] == ('~9\x1b','home-errand:request-knowledge:identification')`: that outside request is already corrected and owner must remain home-errand. Retain boundary/Observe/violation controls. No specified flip; cut replay at an earlier newly changed key if one arises, with its actual tuple pinned before dispatch rather than extending a synthetic suffix. |
| D2b/D3b | `test_worldmap_key_hygiene.py::test_world_map_preempts_every_retained_town_owner_family` retains world-map gate over old Home alias; `test_two_fresh_instances_have_the_same_world_map_gate` retains fresh-instance parity. No flips. |
| D2b | `test_xbow_pref_recorded_divergence.py::test_tpstockout_first_decision_is_the_crossbow_swap`, `test_classC2_first_decision_is_the_crossbow_swap`, `test_live27_first_divergence_is_the_crossbow_target` retain physical Home weapon take/target. No flips; outside catalogue shortcut does not suppress known physical transactions. |

D1's projection test is Home-required and stays true; extend it with an
outside-only action whose `equipment_work_need_present` is false. D2a's known
existing producer flips are the live23/catcycle assertions above. D2b and
D3a/D3b keep the existing alias controls and add R13/R9/R11/R12 regressions,
including baseline-no-credit, external displacement, same-owner bounce,
stationary interruption and exhausted own-decision bounds. D4's moved-address
assertions explicitly flip, while correlated requests, actual mutation and
absent target controls remain. D5 changes the recorded scheduling pin, not the
existing genuine-uncomposable tests. All slices retain the Every slice burst
and typed-defect tests above; D6's sole new test waits for A.

The historical-characterization tests
`test_town_approach_retired_recorded.py::test_recorded_walk_closes_its_claimed_distance_and_is_retired`
and `test_q2travel_progress_recorded.py::test_recorded_walk_retired_quest_request`
describe old logs. They do not flip; their current-code continuation controls
and newly extracted step-2 tests do. The earlier review specifically warned
against naming extractor-only tests as existing; this design does not do so.

## Returning log-only to enforcing: gate and measurement

**Not safe now.** The 16 events include both false accounting and two real
burst scenes; CL45's lack of escalate is not sufficient. Disabling log-only
would stop at R1 before reaching the later work. Zero retirement produced by
new endless waits would also be a failure, not qualification.

Proposed gate, preserving the owner's all-kind requirement:

1. Offline implementation qualification: every all-kind table row reconciled
   to actual producers and final driver sends; zero unmapped town work and
   unexplained ownership violations. Positive/negative controls cover observed
   success, impossibility, stale/duplicate observation, safety, bookkeeping,
   prompt/tail, fresh-process restart and alias rewrites. Existing replay
   checkpoint compatibility is separate from restart memory. All 16 incident
   pins explained on the qualification version, including separate R4
   classification and A's R14-R16 result; D alone cannot claim those resolved.
   Accounting defects no longer
   retire; impossible/dead offers end once with the existing concrete outcome;
   forced stalled/reversible controls still visibly fail within their bound.
   Existing ON ownership corpus must pass before any ON/OFF migration. This
   task does not change the ownership flag or execute that corpus.
2. **D0 is a prerequisite to starting the measurement clock.** Log a
   process/session ID, build version and visit epoch before counting active
   exposure; join decision rows to `autorecover.jsonl` and last captured
   `in_town`. A restart creates a fresh process/visit identity, never imports
   D state; the external evaluator still counts restarts across processes.
   D diagnostic cohorts may start without A; D6 waits for A and A's qualification
   is measured separately. The final enforcing switch requires both results
   plus R4 resolution. Live shadow/log-only on one recorded qualification
   version: **24 active
   live hours in each cohort**, CL45-like and low-level (48 total), at least
   20 consecutive completed town visits and 3 completed dives **per cohort**.
   If hours elapse without exposure, continue until visit/dive minimums are
   met. Paused/stopped time is reported separately, never counted as active
   exposure. Any unclassified retirement, reopen or false failure resets
   that cohort's consecutive qualification interval. Fix/revision change
   starts a new interval; don't combine earlier good suffixes. No artificial
   waits, forced departures or omitted events to meet a numeric gate.
3. Require zero raw unexpected pending retirements, zero unexplained
   `would_retire/retired`, zero `owner-retired-log-only` events for actual
   errands, and zero retirement bursts during those qualifying live windows.
   Truly forced negative tests are separate from live denominators and cannot
   be excluded from a live failure count. Existing genuinely impossible work
   should use its specific visible outcome, not repeated owner-retired.
   Bookkeeping-only events are separately counted; if they recur, fix their
   erroneous admission/accounting before removing compatibility, since the
   enforcing CLI currently stops on them too.
4. Preserve overall plan goals: escalate 0; at most 3 town restart/stop events
   per 24 active live hours for **all reasons**, counted using last captured
   `in_town`, not floor level. Report dungeon/wilderness separately. A town
   no-progress alternation with no retirement fails the gate. Detector: D0
   joins producer/operation/target within a process/visit, and increments an
   own-decision counter when no matched effect or qualified BFS minimum occurs.
   Alias/claim changes, self-bounces, repeated page opens and A->B->A target
   cycles without a new obligation cannot reset it; externally caused route
   re-baselines grant no reset either. Fail at the child's existing unsuccessful
   allowance (physical travel/equip/take/buy 8, Q2 3, detector routing 2, other
   kinds at their all-kind table bounds) if no completion or concrete failure
   record exists at that boundary. Pending posted tails use their existing
   deadline, not an endless zero-count wait. For ownerless/unmapped cycling,
   use the existing CLI fuses as additional detectors: blocked streak reaches
   `TOWN_BLOCKED_STOP_LIMIT = 30`, or residence reaches
   `TOWN_RESIDENCE_STOP_LIMIT = 1500` decisions; either actual fuse stop fails
   qualification even when no retirement occurred. Any unmapped own decision
   is already a Gate 1 coverage failure. These are measured thresholds, not
   new runtime stop rules; D0 observes counts even in log-only. Every pending
   bounded work must complete or record failure within its allowance. Also
   check no new departure weakening and
   no optional cleanup converted into a mandatory defect stop.
5. After both cohorts and offline gates pass, propose the concrete switch
   removing `--owner-retired-log-only` from the runtime invocation (or changing
   compatibility behaviour in a separately reviewed patch). Keep retirement
   as a visible last-resort stop, and retain explanatory receipts. The owner
   must authorize that future runtime action; this design authorizes no
   control. The burst need not be deleted to perform the switch. Re-measure
   the same exposures enforcing; any false retirement fails enforcement
   acceptance and requires recorded diagnosis, not automatic silent waiting.

Counters/joins for that measurement:

| Counter | Existing evidence / addition in D0 and subsequent slices |
| --- | --- |
| Run version, active hours, visit completions, dives, town hours | Session/restart markers, timestamps, state `in_town`/town/floor; explicit version and visit epoch receipt added because old decision rows have no reliable build field. Record stops/downtime and coverage gaps. |
| Retirement events by producer/work and trigger | Retirement JSONL time/turn plus added sequence/event ID; decision `arbiter.would_retire`, `retired`, `retirement_set`; deduplicate repeated flags and overlapping gzip files. Count raw events before forgiveness, not just stop reasons. |
| Burst count and productive resets | Existing `retirements_without_progress`, `forgiven`; log matched receipt identity and minimum before/after, counter before/after, and original/final reason/key. A reset with no qualifying proof is a failure. |
| Successful child/root completion; attempted impossible work | Causal receipt keyed to operation/target, one-time outcome + cause, consumed obligation and producer site. Track repeat same-work offers after impossible/done at unchanged input; expected 0. |
| Unbounded awaits / alternations / false credit | Own unsuccessful-decision count and bound, active pending operation/finite tail; repeat target cycle without new obligation/effect; duplicate/mismatched credit count 0. No reliance on changing turn or fuel name. |
| All-reason town stops/restarts/escalates | `autorecover.jsonl` event plus captured last `in_town`; report independent policy final stops as well, so suppressing retirement cannot hide another stop. |
| Unmapped sends and contract defects | Existing `town_work` driver/policy-final validity and claim violation diagnostics; versioned all-kind observer coverage, including driver ESC overrides and poll/tail paths. |

The historical 6.05/2.82-hour windows are diagnostic evidence, not parts of the
new qualification period. Zero counters require demonstrable work exposure;
absence of a rare category in live play is covered by offline pins and is
reported as such, never described as live proof. These conditions define when
the future switch is justified without promising that this design has already
met them.

## Design completion record

Delivered all 16 records: 15 in disjoint diagnosis groups and R4 explicitly
unclassified/excluded. Exact source paths (and trigger ambiguity), finite
observed-progress rules,
minimal producer/accounting remedies, mergeable implementation slices, real
existing test names and a measurable enforcing gate. Prior slice-1 bookkeeping
and burst semantics remain. Step 1.5's full-Home sale/closure fixes are not
reintroduced as a generic tombstone framework. R14-R16 are unchanged and
handled by A; D6 is a single post-A capture
control. R4 remains explicitly excluded until classified. D diagnostic
measurement is independent of A, while final enforcement still requires the
all-kind qualification, R4 resolution and separately qualified A result.

Only this document is intended for this task's commit; the supplied plan,
measurement files and evidence remain inputs. No implementation, tests, live
operation, push or merge was performed.
