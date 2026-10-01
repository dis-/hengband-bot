# Equipped character-sheet calibration design

Date: 2026-10-01. Design only; no source or test modifications and no test suite execution.
Bot baseline: `3e153bc106119624307bd53fc25803049271ff21`, branch `calib-design`.
Game references below are relative to `C:/hengband/`; inspected local game HEAD is
`8c1cff9310d28f3a793138c415b4c65eb4814086`. Bot references are relative to this worktree.
Line numbers refer to the inspected files, not a promise about future revisions.

The user approved 「全部この方針で進める」: replace depositing, stripping,
naked capture, re-equipping and supply restoration with observations made while
equipped. Adopt that direction. Do not start new strip sequences in the new mode.
Keep a bounded migration executor for physical debts already incurred by an old
process. Calibration becomes a cheap observation, independent of Home and town.

## 1. Findings and scope

Ordinary, undrained Warriors can be calibrated without removing equipment using
the visible stat table, permanent `@` flags, displayed HP/AC and identified equipment.
However, **not every old field is directly or uniquely observable from every C
screen**. A universal implementation based on subtracting equipment from totals
would be wrong:

* `基本/Base` is natural **maximum**, not drained natural current. `現在/Current`
  is effective current after adjustments. `stat_cur` is not printed when drained.
* `装/Mod` is a residual including mutation/other adjustments, not just equipment.
  The residual itself loses information at the minimum-stat floor.
* `18/***`, red/green digit colors, `s`, and `*` lose different information; a
  plain-text dump cannot always replace a colored screen observation.
* HP has a level-dependent floor; AC has exceptional equipment interactions.
  A constant recovered from an unsupported loadout is not reliable.
* C's `@` is source-separated, so equipment need not be removed to see intrinsic
  flags. But a temporary form can change what the emitter calls permanent.
* Existing JSON `character.stats[].maximum` is **the disclosed natural ceiling**,
  not the `基本` column. The existing character payload does not contain the full
  six-column table. Do not rename that field and assume the problem is solved.
* The old record folds pinned cursed equipment into numerical constants, while
  the optimizer also retains pinned equipment. Schema migration must address
  this double-counting risk explicitly.

Recommended initial support envelope: Warrior, ordinary stable form, undrained
stats, no temporary stat/HP/AC effects, complete visible observations, identified
current equipment, and a supported armor calculation. Outside it, return a typed
unavailable reason, retain safe current equipment, and request the smallest missing
visible observation. Do not create a Home trip, retry loop, mandatory purchase, or
strip fallback. Extend the envelope only after recorded evidence supports it.

### Field-by-field contract

The current record is at `src/hengbot/warrior_optimization.py:117`, construction at
365, serialization at 440/455, and staleness at 149. “Mode” below means the game's
internal C display mode (`src/view/display-player.cpp:57`); recognize page headers
rather than assuming a fixed number of navigation keys.

| Field | Visible source with equipment on | Derivation / limitation / proposed semantics |
|---|---|---|
| `race_id` | Race/種族 title on identity page and mode 2 | Map displayed localized title to the existing public ID dictionary. Form/race title must be part of the observation signature. A transformed title does not reveal a hidden underlying race; defer ordinary calibration in that case. Emitter titles: `src/bot/bot-json-output.cpp:1984`. |
| `class_id` | Class/職業, identity page and mode 2 | Public title-to-ID mapping, same scope restriction to Warrior; emitter line 1985. |
| `personality_id` | Personality in the identity/name line (e.g. ちからじまんのbot-test) | Map localized displayed personality; `character.personality_title` at emitter line 1986. Do not infer from equipment/stat totals. |
| `level` | Level/レベル on main page or mode 2 | Exact displayed integer. Bind to the same observation epoch as all other values. |
| `stat_cur` | Mode 2 Base, stat name's drained mark, Current and Actual | Undrained: natural current equals Base. Drained: generally not uniquely recoverable; retain a **tagged visible observation key**, not invented raw current. Existing protocol-3 key is signed `stat_max` (`src/hengbot/model.py:413`), which misses further drain while already drained. V2 also records effective Current and the full visible row signature. Do not compare a raw-v2 tuple to a printed-key tuple without a kind tag. |
| `base_stats` | Mode 2 six stat rows: Base/Rac/Cla/Per/Mod/Actual/Current, intrinsic modification column, mutation descriptions and equipment details | Forward calculation below. Never set this to Base alone, nor invert effective totals blindly. Exact for supported undrained observations; ambiguous drain/floor/capped values return unavailable. V2 means intrinsic-only effective stats, excluding even pinned items. Preserve raw Base plus additive intrinsic adjustments for evaluation. |
| `base_hp` | Main page HP maximum, equipped effective CON, level; visible temporary-effect indications | Derived below. Not directly printed, nor universally identifiable when HP is floored or temporary effects are not separable. Retain distinct HP model metadata; old `base_hp` is a residual after naked CON subtraction, not simply the game's hidden rolled HP. Never read `player_hp`. |
| `base_ac_bonus` | Main page AC `[base,+bonus]`; equipped effective DEX; visible `e`/item descriptions and `~f` shield proficiency | Derived below. Complete, supported displayed equipment contributions required. `TR_NO_AC`, unknown curse strength, set effects and unsupported armor interactions cannot use ordinary subtraction. V2 excludes all item contributions, including pinned items. |
| `intrinsic_abilities` | Mode 2 resistance/utility `@`; mode 3 telepathy `@`; mode 4 where relevant | Read intrinsic source only; map semantic rows to ability names, using current permanent `ability_sources` only if observation-bound and demonstrably the same display source. Do not OR equipment or temporary columns. `warrior_optimization.py:599` currently prefers source detail; make its freshness explicit. Spell-supplied requirements remain a separate gate (success >=90%), not fabricated intrinsic flags. |
| `pinned_identities` | Equipment slots, visible curse row/known curse message and identified item identity | Sorted `(slot, equipment_identity)` using `equipment_identity` as today. Pins constrain transactions, not the intrinsic constants. Unknown removability is unknown, not permission to remove. Empty when no known cursed items. No takeoff experiment. |
| `observed_turn` | Character-response envelope's observation turn | Provenance metadata, not a hidden character property. Carry envelope turn/sequence through CLI; do not use latest unrelated movement turn or file mtime. |
| `mutation_signature` | C mutation page (mode 5), or the corresponding visible mutation list in the dump | Sorted IDs mapped from visible descriptions; empty observed list differs from missing list (`None`). Existing `character.mutations` may supply this only within that visible scope. Unknown/new text must invalidate support, not silently disappear. |
| `intrinsic_tr_flags` | Modes 2–4 intrinsic `@` marks with row, symbol and color, plus mutation/form context | Semantic interpretation below. Equipment source remains separate even when it duplicates `@`. Exclude temporary source. Preserve explicit immunity/vulnerability meanings; do not just collect a resistance row's ID whenever any boolean is true. |

### Exact stat arithmetic and its limits

Use `M(v,n) = modify_stat_value(v,n)` from `src/player/player-status.cpp:2952`:
each positive step adds 1 below 18, otherwise 10; each negative step subtracts 10
at >=28, maps 19..27 to 18, subtracts 1 at 4..18, and stays at 3.
Parse `18/nnn` as `18+nnn`. `18/***` is an interval >=238, **not an exact 238**
(`player-status.cpp:2922`). Do not exploit raw JSON values beyond display precision.

For stat i let N be displayed Base, R/C/P the displayed racial/class/personality
adjustments, U the non-equipment adjustment reconstructed from visible mutation
descriptions/known stable form, and E the sum of known item stat pvals:

```
I = R + C + P + U
intrinsic_base_stat = M(N, I)                       # undrained supported case
predicted_equipped_stat = M(N, I + E)               # apply once from N
legacy_pinned_base_stat = M(N, I + E_pinned)        # comparison only
```

`src/player-status/player-basic-statistics.cpp:101` computes top from natural
maximum and the combined adjustment; line 133 computes use from natural current.
The stat index is `v-3` at <=18, `15+(v-18)//10` at <=237, otherwise 37
(same file:154). Use the game's truncation rules, including C++ truncation toward
zero for negative integer division.

The displayed residual is obtained by `calc_basic_stat` at
`src/view/display-player-stat-info.cpp:35`: for natural maximum N and top T,

```
Q = (T-N)/10                      if N>18 and T>18
Q = T-N                           if N<=18 and T<=18
Q = (T-18)/10 - N + 18            if N<=18 and T>18
Q = T - (N-19)/10 - 19            if N>18 and T<=18
Mod = Q - R - C - P
```

All divisions here are integer truncation. The racial column includes Ent level
adjustments (line 64), and process_stats subtracts R/C/P at line 148. Consequently
`U = Mod-E` is permitted only after proving no loss at a floor or exceptional
transformation, and verifying forward reconstruction. Forward reconstruction alone
does not prove uniqueness at a floor: N=3, I=-2, E=2 and N=3, I=0, E=0 can both
display 3 but differ under future gear. Prefer R/C/P plus known mutation rules;
use Mod as a consistency check. Reject unknown residuals.

Stat `@` mutation symbols are computed at lines 254–395 and can be overwritten by
`s` for sustain at line 400 onward. Negative and positive digits differ by color;
`*` means magnitude >=10. Thus mutation descriptions or item inspection are the
smallest alternatives when a glyph is ambiguous. Do not interpret `s` as zero
mutation adjustment. Special CHR overrides need separate support.

For drained stats, find all natural currents consistent with Base, Current and
known combined adjustments. Accept only if all candidates produce the same
counterfactual values for every evaluated loadout; otherwise defer optimization
until ordinary recovery or a newly informative screen. Do not force restoration
shopping just to calibrate. A saturated Base likewise represents a set, and an
unbounded/unsupported set must be unavailable, not guessed.

Consumer change is essential: `warrior_equipment_evaluator.py:362`,
`warrior_defense_evaluator.py:159`, and `warrior_loadout_evaluator.py:142` currently
apply item modifiers to an already modified base. In general
`M(M(N,I),E) != M(N,I+E)`, e.g. N=23, I=-1, E=1 gives 28 versus 23. Carry N and I
in v2 evaluation inputs and apply the total once. Retain `base_stats` as a derived
compatibility/report field. A matching base-stat tuple alone does not certify
candidate damage, blows, CON or DEX correctness.

### HP and AC formulas

For an ordinary Warrior without temporary HP effects, define
`B(v,L)=trunc((adj_con_mhp[index(v)]-128)*L/4)` and `F=L+1`.
`src/player/player-status.cpp:412` computes `H=max(F,R+B)` before temporary
heroism (+10), berserk (+30), tsuyoshi (+50), and hex additions (+15/+60), at
lines 443–456. Other classes/forms have additional handling at 419–437.

For a displayed equipped maximum H strictly above F, and no temporary HP effects:
`R=H-B(CON_worn,L)`. Predict the old stripped (or pinned-only) observation with
`H_old=max(F,R+B(CON_old,L))`, then
`base_hp_old=max(1,H_old-B(CON_old,L))`, exactly as old calibration at
`warrior_optimization.py:404`. This includes the possibility that stripped HP
hits the floor even though equipped HP did not. Store R plus the floor rule in
the v2 model; do not confuse R with the old residual in this case. When H=F,
R is only bounded above: no exact unique residual is guaranteed. Defer or use
candidate-set unanimity, never read the game's hidden HP roll array.

`warrior_loadout_evaluator.py:138` currently uses `max(1,base_hp+B)`, which does
not implement the game's `L+1` floor. Correct the v2 path with the model above;
record legacy residual equality and predicted HP equality separately. Current HP
need not be full merely to read maximum HP; the safety scheduler still owns when
to open C. Full health is not a new calibration trip or waiting requirement.

For ordinary armor, let `A=displayed_base_ac+displayed_ac_bonus`,
`D(v)=adj_dex_ta[index(v)]-128`,
`S=floor(shield_skill*(1+floor(L/22))/2000)` if either hand holds a protector,
and `T=5` if the sub-hand has known supportive. Then

```
K = A - D(DEX_worn) - sum(item.ac + displayed_item.to_a) - S - T
AC(candidate) = K + D(DEX_candidate) + sum(candidate.ac + candidate.to_a)
                + S(candidate) + T(candidate)
```

References: `src/player/player-status.cpp:1622` base/shield,
1647 DEX/form/class, 1687 item enchantment and LOW_AC curse, 1709 supportive,
1714 race, 1719 artifact sets, 1731 mutation armor; bot formula at
`warrior_defense_evaluator.py:152`. Use the displayed AC pair (emitter:1990),
not hidden true AC. Accept only complete known item contributions and supported
interactions. Ordinary mutation/race armor remains in K; temporary effects must
be absent. `yoiyami`/NO_AC zeroes the total and destroys invertibility; LOW_AC
curse magnitude is explicitly rejected by the current evaluator. Artifact set
AC bonuses cannot be folded into an intrinsic K. Either implement the visible
named-set contribution symmetrically for current/candidate sets or defer it.

Legacy pinned comparison uses `AC_old=K+D(DEX_old)+item_AC(pins)+S(pins)+T(pins)`
and `base_ac_bonus_old=AC_old-D(DEX_old)`. V2 stores K and counts pinned items once.
Do not demand K equal the old pinned residual. Unknown enchantment or curse
details require visible identification, not raw object flags.

### Flag semantics and combat validation

`src/bot/bot-json-output.cpp:869` separates known equipment, permanent
`player_flags`, and temporary `tim_player_flags`. The table at 1713/1853/1870
adds immunity/vulnerability columns. Those latter booleans are **keyed by the
resistance row**, e.g. `player_immunity` maps IM_FIRE to RES_FIRE and
`player_vulnerability_flags` maps VUL_FIRE to RES_FIRE
(`src/player/race-resistances.cpp:20,113`). The existing helper at
`warrior_optimization.py:341` merely adds the row's `flag_id`; that is insufficient
for interpreting a vulnerability as TR_VUL_FIRE or immunity as TR_IM_FIRE.

Normalize (row, source, mark, color) to semantic resistance/immunity/vulnerability
sets. Preserve an explicit nether-immunity capability if there is no matching TR
constant; do not invent one. Temporary immunity and stance-derived vulnerability
must not be frozen into permanent constants. An active form also changes the
“permanent” source (emitter comment:883). Cache stable-form observations only.
Missing rows are unknown; explicit complete rows of dots are false.

The plain dump may hide distinctions conveyed by color/temporary overlays. Use
structured visible source data or colored screen cells for those cases; require
a neutral-effects capture for initial support. Keep legacy flag extraction as
a comparison diagnostic only, documenting corrections instead of preserving a
known false resistance. All 19 existing ability names must be covered, including
see-invisible (which is not in `PLAYER_ABILITY_FLAGS`); derive the mapping from
the established visible ability schema rather than that incomplete dictionary.

Do not use C's attack bonus as a new raw combat constant. Its to-hit includes
`skill_thn/3` and known weapon to-hit (`src/view/display-player-middle.cpp:41–54`).
For comparisons remove those contributions exactly once; to-damage has its own
known weapon addition. C average damage is not expected damage against AC 100.
Preserve the required AC-100 per-turn evaluation and blows calculation. Weight
is not an equipment comparison criterion. Keep the authoritative depth gates:
20 FA/fire; 21–25 FA/confusion/fire; 26–30 poison/cold/electricity/acid;
31–39 chaos; 40–49 chaos/nether; 50–80 also telepathy/destruction; 81+ also +25
speed and as many resistances as reasonable. No new speed gate below 81F.

## 2. Acquisition, parsing, and freshness

Reuse the existing 180-second periodic request (`cli.py:119`),
`request_character_dump` / `_periodic_character_dump_key` (`policy.py:9662,9689`),
and macros `Cf\ry\x1b\x1b` / Home `Cf\ry\x1b`
(`policy_constants.py:106`). A C dump contains all pages, so do not add repeated
page navigation unless direct colored-screen fallback is required. In a direct
screen reader recognize identity, mode-2 stats/resistances, mode-3 ESP, mode-4
sustains and mode-5 mutations by headers and complete-row checks. Leave C through
the existing prompt executor. Do not inject this macro into a pending item/store
prompt, combat response, or posted transaction.

The JSON response already includes a player snapshot, equipment and `character`.
`cli.py:4957` currently discards the envelope and calls
`observe_character_snapshot(character)`; extend that call to supply turn,
response sequence, protocol version and the matching visible snapshot.
`policy_observation.py:28` must assemble an observation for every suitable C
response, instead of collecting flags only during naked capture.

Existing usable character fields: `race_title`, `class_title`,
`personality_title`, `base_ac`, `ac_bonus`, `stat_modifiers`, `curse_marks`,
`mutations`, `characteristics`. Snapshot provides level, HP and displayed current
stats. `character.stats[].top` is effective maximum; `.maximum` is the natural
cap conditional on knowledge (`bot-json-output.cpp:1882,1901`), not Base.

Smallest missing transport: add a versioned visible `stat_table` projection to
the emitter in a later implementation, factoring the **same display formatter**
used by `display-player-stat-info.cpp:148,420`. Per row carry `stat_id`, printed
Base/Actual/Current (including saturation), Rac/Cla/Per/Mod integers, drained
marker, and existing slot/`@` symbols/colors. Never export raw `stat_cur`,
`stat_add`, undisclosed ceiling, item flags, HP rolls or true AC. Until available,
parse the actual completed dump's six-column text as a fallback with a matching
response token and changed content hash; a merely existing `bot-test.txt` is not
fresh evidence. Missing numeric columns in old protocol recordings must remain
missing, not be reconstructed using privileged historical fields.

For text, decode local dumps strictly CP932 and JSONL strictly UTF-8; select an
explicit JA/EN layout from headers (`基本 種 職 性 装 合計 現在` versus
`Base RacClaPerMod Actual Current`). Parse fixed display-cell columns anchored by
the headers, not whitespace token counts: current may be blank and JP glyphs use
two cells. Normalize full-width HP/AC labels, stat row aliases, signed numbers,
`!`/drained names and 18/xx. Do not merge equipment slots across pages without the
same equipment signature. Reject duplicate, truncated, unknown or inconsistent
rows with a specific reason; preserve raw evidence for diagnosis.

Proposed observation state: idle -> requested -> posted -> complete or rejected.
One coalesced request per visible invalidation; one bounded retry after timeout
at a later safe opportunity, then wait for the next periodic request or changed
evidence. Use response sequence/request correlation, not turn alone (C can be
zero-energy). Only posting acknowledgment creates an in-flight request. Atomic
record publication follows full validation; no partial stat/flag merge from two
epochs. Cache the last rejection signature to prevent repeated parsing/log spam.

Staleness: identity/form, level, Base, effective Current, drained marker, mutation
list, intrinsic row signature, known pinned set, relevant effects beginning or
ending, equipment identification/enchantment changes during acquisition, protocol
or parser schema change, and game/session identity changes. A normal equipment
swap does not invalidate intrinsic constants once verified, but changes the
observation consistency key and optimizer inputs. Candidate plans are invalidated
when their calibrated inputs change. A periodic complete dump audits unexpected
changes; stale/unknown never means zero flags. `stale_reason` and optimizer
preparation must consume the same evidence key rather than the latter dropping
mutation checks (`warrior_optimization.py:663`).

Retain typed failures such as `visible-base-missing`, `drained-ambiguous`,
`saturated-stat`, `hp-floor-ambiguous`, `unsupported-ac-interaction`,
`temporary-form`, `snapshot-mismatch`. They disable affected optimization, not
survival actions or ordinary travel. A descent still requires positive evidence
for the unchanged depth requirements; an unavailable calibration is not a new
unconditional departure conjunct or a reason to descend without gate evidence.

## 3. Removal and migration inventory

Implement observation/recovery separation first. Delete legacy operational paths
only after no new strip can start and old physical debts have a migration owner.
The following is the concrete search/removal inventory, including references
whose names do not contain `calibration_`:

| Area and inspected references | Required disposition |
|---|---|
| `policy_calibration.py:58,266,391,724,773,832,906,1093` | Replace validation/capture with observation service. Remove deposit/strip/capture/restore-equip/restore-supplies initiation, town preconditions, visit limits, abort/rearm/deferral machinery. Relocate ordinary stat restoration helpers at 293/323/374 only if still independently useful. |
| `policy_calibration.py:157,180,233,486,566,636` | Move persisted redress import, accounting and observed completion into a temporary legacy-recovery adapter. Do not clear physical debt to make the new design appear complete. |
| `policy.py:2302–2359,2425,2605` | Replace phase/restore maps, counters, signatures and naked-dump latches with explicit observation state plus migration debt. Update fresh construction and restored-state normalization together. Retain calibration file-path isolation. |
| `policy.py:3014,3236,3562,3817,4254,5777–6069,6328–6579,6745,6938,7444,7492,7658` | Remove special town priority, family gating, continuation matching, claim resumes, routing and foreign equipment-session suppression once migrated. Keep ordinary transaction prompt acknowledgment and ownership rules. |
| `policy.py:7858–8054,13470` | Remove restore-batch accounting from ordinary Home observations and replace naked dump send latches with observation posting. Migration adapter alone receives old pending operation acknowledgments. |
| `policy_home.py:20–177,591,626,1286,1318,1543–1562,1616–1753` | Remove restore quantities/protection, kept-Home projections, deposit-created debt, special withdrawal identity matches, redress page-gap search, owner overrides and reservation exclusions. Preserve generic Home catalog, page scanning, atomic quantity and move-identity handling. |
| `home_visit.py:294` | Remove calibration restoration exception only after migrated Home debt uses the ordinary recovery path. |
| `policy_equipment.py:661,1447,1777,1830,2136,2180,2217,2367,2934` | Remove calibration producer relabeling, session exclusivity and deferral conditions. Keep normal optimizer and confirmed equipment transaction behavior. |
| `policy_quest.py:462,475,1041`; `policy_shop.py:1386,1414,3720,3741,4412`; `policy_fundraising.py:1061` | Remove calibration deposit/restore errands and reserved withdrawals, shop family translation and fundraising suppression. Replace only the optimizer-readiness use with explicit observation readiness; do not discard quest or supply obligations. |
| `policy_town.py:1647,1706,1709,2289,3195,3228,3683,4894` | Retire `calibration_loadout_restored`, `calibration_phase_complete`, `calibration_restore_complete` and calibration Home routing/reservations. While legacy debt exists, use a separate `legacy_recovery_complete` condition with a real executor. Ordinary sessions never receive it. |
| `claim_ladder.py:102,119,319`; `claim_goal_typing.py:130,310–321,684`; `town_arbiter.py:140,609`; `ownership_metrics.py:1137` | Retire calibration errand family, operation row, travel/observe goal mapping, registry/stall budget and metrics exceptions. New C observation belongs to existing bookkeeping knowledge requests with posted/observed settlement. Legacy family is accepted only by the checkpoint adapter until removed. |
| `policy_observation.py:28,91`; `cli.py:1305,3107,4957`; `runtime_paths.py:27` | Replace naked handler and visit reset telemetry; preserve request scheduling, runtime path isolation and diagnostic reporting. Report source/schema/unavailable reason rather than a strip phase. |
| `warrior_optimization.py:117,281,341,365,440,455,647–751`; optimizer/evaluator inputs | Version record, pure derivation, semantic flag handling, same evidence freshness at selector boundary; bump optimizer key schema and invalidate confirmed records/caches. Remove naked-only assumptions and count pinned gear once. Keep search constraints and transaction planner. |
| `latch_onset_capture.py:119–160,416`; `policy.py:2605` | Centralize idempotent state upgrade before choose/observe/shadow calls and capture probes. No new attribute may exist only in `__init__`. Update calibration entry-state diagnostics to observation/recovery equivalents. |

Implementation completion audit: search the entire tracked tree for
`calibration`, `redress`, `naked`, `strip`, `restore-supplies`, `restore-equip`,
`CALIBRATION_HOME_VISIT_LIMIT`, `_calibration_restore_kept_home` and
`_calibration_restore_protected`. Classify every result as new observation,
legacy migration, unrelated feature, historical fixture, or obsolete; no active
unclassified execution branch may remain. Update docs, static ownership catalogs,
reason registries and extractor manifests along with code. Historical evidence
is retained, not rewritten to match the new behavior.

### Persisted records and checkpoints

V2 proposed record envelope: `schema_version=2`, `source=equipped-c-screen`,
session identity, evidence turn/sequence/hash, language/parser version,
`stat_key_kind`, exact-or-interval visible stat rows, raw Base and intrinsic
adjustments, HP model kind/floor, AC support kind, source-separated intrinsic
capabilities, and the 13 compatibility fields above. Persist atomically by
temporary sibling plus replacement; do not overwrite the only recovery journal.

Old numeric records have no trustworthy new schema tag. Preserve as read-only
comparison evidence, invalidate as v2 optimizer input, and request a fresh C.
Do not mechanically rename old pinned constants or fill absent new fields with
zero. `save_character_calibration` currently serializes the calibration itself;
ensure publication cannot erase a `redress_obligation` stored in the same old
file. Extract and durably save that obligation **before** replacing the record.

Checkpoint upgrade rules:

1. Normalize all new fields with explicit defaults in a shared idempotent upgrade
   used by `restore_checkpoint`, direct policy unpickle/resume, and entry-point
   guards. Proposed defaults: observation schema=2, pending=None, evidence=None,
   rejection=None, retry=0, recovery journal empty only after inspecting legacy
   state. Do not run the full constructor over a restored object.
2. Inspect phase AND suspended phase, worn-before, stripped-unrestored, restore
   signatures/items/outcomes/move IDs/quantities, session target, atomic Home
   pending operations and file redress obligations. Even `phase=None` can owe gear.
3. Reconcile a posted command against the next real observation before any resend.
   Translate remaining worn identities and deposited supplies to one recovery
   journal with quantities, destination and known item identities. Retain Home
   reservations and departure protection only for this journal. Recovery may
   need a final Home visit; new calibration never does.
4. Complete required re-equipping and supply reconciliation through the existing
   equipment/Home transaction machinery with observed effects. If an item cannot
   be found, retain unresolved debt and diagnose it; do not fabricate successful
   restoration or delete the journal. Avoid repeated unbounded travel retries.
5. After observed recovery, retire old claims, continuations, reservations and
   calibration-owned sessions, then acquire equipped C and clear old latches.
   Keep old class/field deserialization compatibility for the migration window.
6. Invalidate cached optimizer keys, confirmed-loadout key and evaluator inputs
   after semantic upgrade. Ignore old pending observation requests after restart;
   obtain a new response. Keep physical posted-command state until reconciled.

Capture artifacts have several restoration styles (for example direct pickle
round-trip in `tests/test_calibration_live33.py:55`). Testing only
`restore_checkpoint` is insufficient. Upgrade twice must equal upgrade once,
including empty debts; new schema initialization must not arm a transaction.

## 4. Evidence fixtures and test plan (not executed)

To honor the design-only prohibition on `tests/` edits, the following are **embedded
fixture specifications**, created here from inspected captures. Later implementation
can extract the exact rows to `tests/fixtures/` without manufacturing a C page.
Hash the original full file and retain row/envelope/raw text with each extracted
fixture. JSON projections below are expected values, not replacement recordings.

| Fixture | Source, 1-based line, observed turn | Verified scope |
|---|---|---|
| `cscreen-equipped-stale-scan` | `jsonlog/incident-20260917-2019-stale-scan-recurrence.state.jsonl:24`, 3148073 | Actual `type=character`, protocol 2, equipped resistance sources, six top rows, mutations empty. SHA256 `cc9ea92ab11353d5efe4ab7460416081e2b3e44e11768a68f81b6cf10b1654b0`. |
| `cscreen-equipped-home-potions` | `jsonlog/incident-20260918-0136-home-potion-trips.state.jsonl:38`, 3221341 | Actual character response; same displayed tops and intrinsic flags, independent envelope. SHA256 `f28e778021c8eaf4ee18a85c2a8515de2bfb27e6e5b57a782df815ecce3cf2bb`. |
| `cscreen-ja-six-columns` | `C:/hengband/lib/user/bot-test.txt`, CP932, stat/flag section beginning at displayed 能力修正 | Full Japanese visible columns, level 28, HP 501/501, AC [19,+56]. SHA256 `0a58ac1d11f21fdce45cbc05ee1fb8b0c90731b6928f497dbf62d39ebc7164a7`. File is a sample, not a response-correlated production record. |

The two JSON captures deliberately lack the new complete `stat_table` and lack
the newer `stat_modifiers`. Expected outcome is flags parsed successfully but
new calibration rejected with `visible-base-missing` unless paired with a genuine
same-epoch visible table. Historical protocol-2 `player.stats.cur/index` must not
be used to fake fair-play availability. Their expected display projection is:

```json
{"top":[150,3,8,48,78,11],"mutations":[],"intrinsic_tr_flags":[10,47,51,52,60,78,80],"full_visible_stat_table":false}
```

In the stale-scan response, cold is supplied by both body and player; poison by
main hand and player; acid by body alone. Pins must show that acid stays outside
intrinsic abilities, while cold and poison survive removing the item source.
This catches dict-as-true, union-of-all-sources and set-difference mistakes.

The CP932 dump yields the following literal row values (STR, INT, WIS, DEX, CON,
CHR order); Current is blank, and the equipment grid has +3 DEX/+3 CHR in slot a:

```json
{"base":["18/66","13","18","18/43","18/27","10"],"race":[2,-6,-6,1,4,-3],"class":[4,-2,-2,2,2,-1],"personality":[2,-2,-1,0,1,0],"mod":[0,0,0,3,0,3],"actual":["18/146","3","9","18/103","18/97","9"],"current":[null,null,null,null,null,null]}
```

For the supported no-mutation/no-pin interpretation, derived base stats must be
`[164,3,9,91,115,6]`; equipped `[164,3,9,121,115,9]`. This is a stat-parser/formula
pin, not proof that all sample equipment interactions or HP derivation have been
validated. Pin individual values against the original visible rows.

Inventory of searched incident recordings: neither
`incident-captures/20260919-2334-prepare-choke-oscillation/snapshots.jsonl` nor
`incident-captures/20260920-0025-choke-vs-loot-oscillation/snapshots.jsonl` contains
a C character page. Do not label them C fixtures. They can remain unrelated
navigation regressions. `jsonlog/replay-20260917-1232-calibration-strip-state.jsonl`
also has no C payload and is migration/strip-state evidence only.
Matches in `jsonlog/sol-events.jsonl:7784,8224` are not used as source C fixtures.
English full tables, colored negative modifiers, saturation, drained ambiguity,
temporary-form and intrinsic immunity/vulnerability captures remain evidence
gaps requiring future real recordings. Clearly labeled arithmetic unit cases may
supplement them, but must not claim recorded provenance.

### Equivalence and consumer checks

Compare against the latest dated persisted strip record inspected here,
`tests/fixtures/live33-character-calibration-20261001.json`: IDs 25/0/1,
level 24, natural key `[75,13,17,39,45,10]`, base stats `[155,3,8,69,115,6]`,
base HP 353, base AC bonus 0, no pins, observed turn 1086413, mutations empty,
flags `[10,47,51,52,60,78,80]`. Older anchor:
`tests/fixtures/character-calibration-20260911.json`, level 26, base stats
`[150,3,8,48,78,11]`, base HP 367, AC residual 0.

These are expected records, **not an already demonstrated equipped/stripped
equivalence pair**. The September equipped C examples are a different level/epoch;
the October sample dump is level 28. Pair only recordings with equal character,
level, natural stats, mutation/form/effects and pin set. Locate an appropriately
matched equipped capture during implementation; otherwise mark comparison missing.
Do not compare numbers across a level-up or silently refresh golden values.

For matched ordinary unpinned observations, require exact equality of all semantic
calibration fields; observation turn/source and explicitly tagged key format are
provenance differences. For pinned observations, compare the **legacy projection**
formulas above to the old stripped measurements, and independently assert that
v2 candidate predictions count pins once. For known flag-parser/floor bugs, report
the old/new difference and visible evidence; do not accept it as an unexplained
equivalence pass. No active stripping is needed for shadow: use already recorded
strip results or existing valid persisted observations with matching epochs.

Required checks in the later implementation:

* Stat boundaries 3, 18, 19..27, 28, 18/219 and 18/***; negative truncation;
  visible drain changing again; mutation+sustain glyph; mixed-sign stat
  modifiers and the single forward-application counterexample.
* HP worn/stripped floor cases, temporary HP rejection, DEX AC steps, shield
  proficiency, supportive sub-hand, known/unknown curses and set armor.
* Source separation for duplicate equipment/intrinsic resistance, temporary
  resistance/immunity, vulnerability-only row and mimic transition.
* Pure equivalent catalog decisions across initial worn partitions; DPS versus
  AC 100 with changed blows; required resistance preservation, unchanged depth
  bands and 90% spell success rule. No equipment weight scoring.
* Missing/partial/mixed-epoch pages, JA/EN parsing, CP932/UTF-8, old protocol,
  missing vs empty mutations, request coalescing, timeout, posted acknowledgments,
  safe opportunity priority, restart and no repeated rejection loop.
* Every old checkpoint phase, suspended phase, no-phase-but-redress, deposited
  supply quantities, foreign session, posted Home operation, missing item, direct
  pickle and normalized restore; interruption at each journal write boundary.
  Assert no new `takeoff`, deposit-for-calibration, Home request or legacy claim
  can originate from v2 calibration.

### Existing test disposition

The *old execution expectations* become obsolete; recorded safety evidence does
not. Rewrite/extract relevant assertions instead of wholesale deleting modules:

* `test_policy_calibration.py`: strip phase/visit/precondition tests -> observation
  lifecycle; retain pure validation and migrate explicit legacy recovery cases.
* `test_calibration_live19.py`, `test_calibration_live25.py`,
  `test_calibration_live28.py`, `test_calibration_live31.py`,
  `test_calibration_live33.py`, `test_calibration_live34.py`,
  `test_calibration_crossarea_debt.py`: new stripping expectations obsolete;
  old debt/checkpoint fixtures remain migration requirements.
* `test_calibration_restore_deposits_recorded.py`,
  `test_calibration_visit_blocked_loop_recorded.py`, `test_cal3_visit_budget_recorded.py`,
  `test_caltravel_recorded.py`, `test_town_calibration_owner_retired_recorded.py`,
  `test_redress_home_page_gap_recorded.py`, `test_restore_stall_recorded.py`:
  old phase travel/owner expectations obsolete for fresh sessions; keep migration
  debt/no-loop/no-item-loss assertions until compatibility retirement.
* Corresponding `extract_calibration_restore_deposits_fixture.py`,
  `extract_calibration_visit_blocked_loop_fixture.py`, `extract_caltravel_fixture.py`
  become historical extraction tools; retain provenance, remove live assumptions.

Must remain green (with intentional schema expectations updated, never weakened):
`test_warrior_optimization.py`, `test_optimizer_purity.py`,
`test_equipment_optimizer.py`, `test_warrior_equipment_evaluator.py`,
`test_warrior_defense_evaluator.py`, `test_warrior_loadout_evaluator.py`,
`test_warrior_loadout_search.py`, `test_ability_sources_incident.py`,
`test_protocol3_client.py`, `test_policy_observation.py`, `test_cli.py`,
`test_equipment_transaction_planner.py`, `test_equipment_transaction_session.py`,
`test_home_visit.py`, `test_home_knowledge_scan.py`, `test_policy_home.py`,
`test_policy_equipment.py`, `test_policy_town.py`, `test_classC_departure_remedies.py`,
`test_classC2_departure_recorded.py`, `test_latch_onset_capture.py`,
`test_incident_artifact_fidelity.py`, `test_resume_inside_store.py`,
`test_runtime_file_isolation.py`, `test_execution_declaration.py`,
`test_emit_ownership.py`, `test_owner_map.py`, `test_ownership_claims.py`,
`test_posted_effect_unobserved.py`, declaration/ownership S2/S3 and town producer
purity modules, and the shared capture/static-name/structure hygiene checks.
Run focused affected modules first, then the repository unittest suite during
implementation. This document's creation runs neither.

## 5. Staged rollout and cost

Estimates below are engineering budget ranges, not measured runtime promises.
Count commands/observations and avoided transactions; dollar costs depend on the
chosen implementation model and are not inferable from the repository.

| Stage | Deliverable and release gate | Cost estimate |
|---|---|---|
| A: visible transport and parser | Full visible columns, provenance, embedded fixtures extracted, missing-data rejection. No live policy switch. | 1–2 engineering days. Reuse one existing dump every 180 s: zero extra game actions; parse six rows and a bounded flag table, linear in response size. |
| B: offline/shadow derivation | Implement stat/HP/AC support envelopes, single-pass stat consumers and schema; compare matched saved strip records and current-loadout screen predictions. No new strip sessions for comparison. | 2–4 days. One derivation per changed observation, not per candidate; diagnostic output only on changes. No duplicate full optimization unless sampled for a specific discrepancy. |
| C: migration and opt-in equipped operation | Upgrade checkpoints, finish pre-existing physical debt, new calibration only C; safe typed unavailable behavior; pass trajectory and ownership checks. | 2–3 days. Fresh sessions: one coalesced dump per invalidation (the macro is 6 ordinary / 5 Home key bytes); no inventory moves. Existing debt: one bounded final recovery sequence whose moves depend on actual remaining items. |
| D: remove legacy initiation/integration | Delete inventory above, retain narrow import/recovery compatibility; observe repeated invalidations, town/dungeon transitions, level-ups and restart. | 1–2 days plus observation time. O(1) request state; no Home reservations or equipment sessions for calibration. Rollback retains v2 journal and never resurrects a strip request. |
| E: retire recovery adapter | Only after supported persisted/checkpoint versions have explicit migration coverage and no unresolved active legacy journals; historical fixture reader may remain. | 0.5–1 day. Removes ongoing branch/counter/claim maintenance cost. |

Total planning estimate: 6.5–12 engineering days including evidence collection and
integration; unsupported class/form expansion is outside this estimate. Schedule
may shrink if the emitter's visible projection is implemented concurrently elsewhere,
but do not assume it exists in this baseline.

Old calibration performs roughly P deposit operations + W takeoffs + one dump +
W re-equips + P supply restorations, plus Home travel/scans and prompt exchanges.
New ordinary calibration performs one dump with no inventory changes: avoids
approximately `2P+2W` item operations plus travel. Count actual sends, game turns,
wall time, parse duration, optimizer invalidations, unavailable reasons, retries,
and recovery debt size in rollout telemetry. Do not claim measured savings yet.

Release gates: zero unexplained differences on supported matched records; exact
current-loadout forward prediction for supported displayed stats/HP/AC; no newly
initiated strip/deposit; no lost old debt; bounded requests; all required depth
gates preserved; focused and full authorized implementation tests pass. Observe
at least one level change, gear change, periodic refresh and restart in the pilot;
record missing scenarios as gaps rather than silently approving them.

Rollback is feature-level: disable new loadout optimization on bad calibration,
keep survival and legacy recovery active, preserve raw evidence, fix/re-read C.
Do not automatically fall back to stripping. The user has already chosen its
removal; ambiguous fields are handled by conservative capability scope and visible
observations. A later proposal to expose new hidden values or resume stripping
would require a different user decision and is not part of this design.
