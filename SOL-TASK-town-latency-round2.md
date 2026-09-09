# SOL-TASK: town latency round 2 — the full same-type inventory, fixed in one pass

User instruction, 2026-09-09: 「町レイテンシの改善には着手して良いが、着手前に同型の問題がないか
洗い出してから」 — permission granted, conditional on sweeping for same-type defects FIRST so this
is not another one-site-at-a-time round.

**The sweep is done.** 24 captured decisions from `jsonlog/home-entry-capture.jsonl` were replayed
through `restore_checkpoint` + public `choose_key` under cProfile. Mean **762 ms per decision**.
Reasons covered: store:entry-await-observation ×5, shop:travel ×4, shop:observe-and-leave ×4,
shop:approach ×2, home:atomic-withdraw ×2, plus 7 singletons.

## The defect type

A derivation that is invariant for one decision, recomputed hundreds or thousands of times inside
that decision. Round 1 fixed exactly one instance (`_fixed_quest_is_offered`, 3,984 calls/decision,
~48% of `choose_key`) by memoising on snapshot identity, cleared at the public `choose_key`
boundary. Per-reason cost fell 25-90%. It was not enough because the same type occurs in at least
seven more places.

## The inventory (calls per SINGLE decision, aggregated over 24 decisions)

| site | calls/dec | self | cumulative |
|---|---:|---:|---:|
| `policy_town.py:12 _refresh_town_facts` | 20 | **2.173 s** | 7.543 s |
| `policy_home.py:371 _retention_reservation_detail` | 860 | 0.242 s | **6.706 s** |
| `policy_supply.py:84 _supply_ledger` | 907 | 0.769 s | 5.025 s |
| `policy_quest.py:867 _quest_carry_target_for_item` | 3,086 | 0.301 s | 1.116 s |
| `policy_quest.py:626 _quest_launcher_ammo` | 3,117 | 0.120 s | 0.430 s |
| `policy.py:5512 _equipped_launcher` | 3,910 | 0.110 s | 0.303 s |
| `policy.py:482 _persistent_grid_signature` | 7,623 | 0.192 s | 0.192 s |

Leaves they drive (symptoms, not targets): `policy_shop.py:152 _store_item_is_supply` 89,306
calls/dec, `model.py:433 is_wand_staff` 47,817, `policy_supply.py:143 <genexpr>` 63,089,
`policy_quest.py:4405 <genexpr>` 33,214, `policy_supply.py:128 <genexpr>` 33,545,
`model.py:457 is_recall_scroll` 26,681, `model.py:465 is_teleport_scroll` 26,165,
`policy_town.py:29 <genexpr>` 20,694 (self 1.322 s — the inner loop of `_refresh_town_facts`).

## Explicitly NOT this type — do not touch

- `policy_navigation.py:951 _build_grid_index` — self 0.538 s but **once per decision**. Its cost is
  algorithmic, not repetition. A separate question.
- `policy.py:2155 _with_grid_memory` (1/dec) and `policy_observation.py:41 _observe` (1/dec) — same.

## The work

Apply the round-1 pattern to the seven sites above, in ONE commit if they share a mechanism or a
small number of commits if they genuinely differ. For each site: memoise on snapshot identity with a
held reference (so a recycled `id()` cannot hit), and clear at the public `choose_key` boundary
before any early return — the existing `_fixed_quest_offer_cache` / `_fixed_quest_head_cache` reset
at `policy.py:2233` is the template.

Work top-down by cumulative time: `_refresh_town_facts` and `_retention_reservation_detail` and
`_supply_ledger` are worth more than the rest combined. If memoising the top three collapses the
others' cost for free, say so with an after-profile and leave them alone rather than adding caches
that buy nothing.

## Hard requirements

1. **ZERO BEHAVIOUR CHANGE.** `decision_equivalence` must report **0 changed decisions** and replay
   must stay identical 400/300. If either moves, the repair is wrong — STOP and report.
2. **Staleness must be impossible, and pinned.** A cache that survives a decision boundary is a
   correctness bug. Round 1's pin
   (`test_fixed_quest_offer_cache_clears_at_public_decision_boundary`) fails with
   `AssertionError: True is not false` when only the two boundary resets are removed — every new
   cache needs an equivalent leak pin. **Some of these derivations depend on policy state that
   MUTATES within a decision** (inventory, retention reservations, pending Home state); if a site is
   not genuinely invariant for the whole decision, DO NOT cache it — say which ones you rejected and
   why. That judgement is the substance of this task.
3. **Derived state, not decision state.** No new cache goes into `home_entry_capture.STATE_FIELDS`
   or the flight recorder. Prove `latch_onset_capture.checkpoint()` byte-size and sha256 are
   unchanged.
4. **Measure.** Re-profile the SAME 24 captured decisions before and after and report mean
   ms/decision plus per-site calls/dec. The round-1 numbers to beat: mean 762 ms/decision.

## Reproducing the sweep

```
cd bot-client; PYTHONPATH=src;tests;scripts
rows = jsonlog/home-entry-capture.jsonl   (269 rows, all with predecision checkpoints)
picks = last 24 usable rows
restore_checkpoint(HengbotPolicy, row["predecision_policy_checkpoint_pickle_b64"])
snap = pickle.loads(base64.b64decode(row["decision_snapshot_pickle_b64"]))
cProfile around policy.choose_key(snap)
```

---

## Live measurement after the 2026-09-10 resume (1,339 decisions, real play)

The profile above came from replayed captures. This is the same question measured **live**, from
`jsonlog/bot-decisions.jsonl` `timing` fields, over the whole post-resume run
(turns 1736334..1840105):

```
             n      choose_key_ms            parse_snapshot_ms         total_ms
                 med    p90     max        med    p90    max        med     p90     max
TOWN       400   272.0 1564.6 1714.3      187.7  262.9  325.0      621.9  2000.1  3779.7
DUNGEON    939    10.6   18.5   63.8       15.5   28.3   68.5       68.9   103.6   322.3
```

**Town runs at 1.61 decisions/sec; the dungeon runs at 14.52. Town is 9.0x slower at the median
and 19x slower at p90.**

Where the town median goes: `choose_key` 272.0 ms (44%), `parse_snapshot` 187.7 ms (30%), the
remaining ~162 ms in poll/read/send.

Two consequences for scoping this task:

1. **`choose_key` is the right target and it is 25.7x its dungeon cost** (272.0 vs 10.6 ms). That is
   this task. The p90 of 1564.6 ms says the tail is much worse than the median, so measure p90 as
   well as the mean — a fix that moves the mean but not the tail has not fixed the felt slowness.
2. **`parse_snapshot` is 12.1x its dungeon cost** (187.7 vs 15.5 ms) and it is **bot-side**, not
   emitter-side. Measured:

   ```
              grids(med)   snapshot_bytes(med)   parse_ms(med)   us per grid
   TOWN          13068            30918             187.7           14.36
   DUNGEON         892            21084              15.5           17.34
   ```

   The town payload is only **1.47x larger in bytes** but carries **14.6x more grids**, and the
   per-grid cost is essentially identical in both (14.36 vs 17.34 us). So the cost is NOT payload
   size and NOT the emitter — it is the bot constructing ~13,000 GridState objects per decision,
   nearly all of which a given decision never consults.

   (An earlier revision of this file called this "emitter-side, out of scope". That was wrong; the
   measurement above corrects it. No emitter change and no separate approval is needed to make grid
   construction lazy or demand-driven.)

   Treat it as a SECOND, SEPARATE task — do not fold it into the `choose_key` work in this pass,
   and do not claim the town is fixed while this 30% of the median is untouched. The same
   GridState-construction cost is what made one captured snapshot 20.7 MB in the purity harness,
   so a fix here likely pays twice.

Report post-fix numbers in this same shape (median AND p90, town AND dungeon) so the improvement is
comparable to the line above.
