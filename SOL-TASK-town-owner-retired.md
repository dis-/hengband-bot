# SOL-TASK: town owner-retired — a stale-knowledge Home-first refusal has no satisfier because the `~9` request bookkeeping latches across town visits and late `~9` responses are dropped

## Revision 3 changelog (designer, 2026-09-12 round 3, after the focused codex re-review `jsonlog/codex-review-town-owner-retired-r2.out.log` = ACCEPT WITH CHANGES, one required change)

Everything codex confirmed in revision 2 is kept verbatim: the three visit-boundary windows, the
dispatcher walk (`_decoded_board_in_town` = `Snapshot.in_town`), the single re-arm per entry, the
A1-seed/A2-seed divergence stops, A1-buy/A2-unit/A2-exit/A2-reentry, the two converted
`tests/test_policy_town.py` tests, no new absorbing state, and the LOCKED user answers (Q1 `~9`
suffices; **Q2 the visible `town:blocked:owner-retired` stays and the purchase claim is not
retired**; Q3 separate task).

**The one required change — a same-visit older response after a Home invalidation and a later `~9`
(codex :461-469, :481-493 vs :511-514).** Decided: **option (B)**, the protocol carries no
request correlation, so the spec forbids a second `~9` while an earlier response can still arrive.

- *Why not (A)*: the emitter's Home listing is `make_snapshot(player) + {type:"knowledge",
  knowledge:{category, menu_key, items}}` (`C:\hengband\src\bot\bot-json-output.cpp:1939-1948`,
  `make_snapshot` :1126-1171 carries `turn`, `player`, `floor`, no emission or request sequence;
  the only HOME emitter is the `~` menu's `9`, `src/cmd-io/cmd-knowledge.cpp:111-113`, and `~` is
  also dispatched inside the store UI, `src/store/store-key-processor.cpp:257-258`). The recorder
  lines / ledger rows carry only `turn` + `items` (`capture-ledger/knowledge-responses.jsonl`, six
  rows 2779969…2816126). `turn` does not order requests: a later request's decision board precedes
  the older response in the stream, so `turn(K1) >= turn(request 2)` is possible (the incident's
  own shape: request at 2781757, response at 2781768 after the queued `3`). Item content cannot
  distinguish two listings either. No derivable correlation → (B).
- *The rule (B)*: **at most one `~9` request is unsettled at any time.** A request is unsettled
  from `confirm_key_posted` until it is **settled** by exactly one of two state-based events:
  (i) the CLI dispatcher walks a `home/9` knowledge line while the request token equals the visit
  epoch (the line is accepted or discarded — either way it settles), or (ii) the visit ends (a
  non-town board line). Soundness: the game consumes keys FIFO, so the response to request 1 is
  emitted before any effect of a key posted after it; the first `home/9` line after the post is
  therefore its response (there is no other unsettled request, and the only HOME emitter is the
  `~9` the bot posts — 6 confirmed posts ↔ 6 ledger rows in the incident, 1:1), and after a visit
  exit the response can only arrive before the re-entry board (the re-entry key is posted after
  the exit board was decided, hence after the request). No counter, no timeout.
- **Mechanism (replaces revision-2 Hunk A2 steps 2-4 and the exit line of
  `observe_town_visit_epoch`):** the token `_home_knowledge_scan_epoch` is minted at
  `confirm_key_posted` (`policy.py:7082-7085`) and cleared ONLY by settlement — the new policy
  method `settle_home_knowledge_request()` called by the dispatcher after any `home/9` line with
  `token == visit`, by `consume_home_knowledge` (the `~9` acceptance), and by the exit branch of
  `observe_town_visit_epoch`. **`_invalidate_home_observation` (`policy_home.py:1663-1683`) no longer
  clears the token** (revision 2 step 3 is withdrawn); it keeps clearing `inflight` (`:1680`), which
  is exactly what marks the pending request *superseded*: `token set ∧ inflight False`. The `~9`
  rung gains one conjunct, `and self._home_knowledge_scan_epoch is None` (beside `policy.py:3147`),
  so no second request can be posted while one is unsettled. The dispatcher predicate becomes
  `inflight_at_arrival and (request_epoch == visit_epoch or request_epoch is None)` (the OR of
  revision 2 is withdrawn); a superseded response has `inflight False` → discarded, then settled.
- **The retry rule `policy.py:3156-3168` is deleted** (its inference "a board after the post means
  the response was lost" is the unsound step codex named; under (B) the visit's request stays
  pending until settled). Consequence, accepted under Q2: a genuinely lost response now ends the
  visit's Home-first attempts after ONE loss — the yield loop → `town:blocked:owner-retired` (the
  visible terminal; measured on the public fixture: four `explore` decisions then the stop). The
  next visit re-arms (A1) and asks again. `_home_knowledge_scan_retries_remaining` becomes a
  write-only vestige (kept for `STATE_FIELDS`/checkpoint compatibility); `HomeErrand
  .observe_scan_refused` loses its only production caller (`home_errand.py:81-84` stays; the
  `home-errand:stopped:knowledge-response-missing` latch can no longer be entered from a lost scan).
- **`consume_home_knowledge` is split**: the open-page path `policy.py:3461-3478` (which calls
  `consume_home_knowledge` at `:3472` and then overrides `_home_scan_source`) must call a new
  sibling `_adopt_home_catalogue(items)` (the current body of `consume_home_knowledge` minus the
  settlement) so that an observed page never settles a pending `~9`; `consume_home_knowledge` =
  adopt + `_home_scan_source = "~9"` + settle. Reason (measured, shadow P5/P5x): a page-made-current
  catalogue followed by a mutation and a second `~9` would otherwise re-open the codex hazard on
  the delayed first response; and tests that answer a confirmed `~9` by calling
  `consume_home_knowledge` directly (`tests/test_policy_home.py:2229-2230`,
  `tests/test_home_light_alternation.py:121-130,786`) keep their HEAD behaviour because the direct
  call settles.
- **New pin A2-supersede** (the pin codex demands): request → real Home invalidation in the same
  visit → the second request is REFUSED while the first response can arrive → the delayed FIRST
  response is REJECTED and settled, the catalogue keeps the post-invalidation state → only then
  the second `~9` → its response accepted. Real CLI consumer, real policy, one instance; the
  invalidation is the public count-contradiction path `policy.py:2594-2603` reached through
  `choose_key` on two Home-page snapshots (no state injection). Lone revert of A2 → HEAD posts the
  second `~9` on the second outside decision and ACCEPTS the delayed first response (measured at
  HEAD: `accepted True, inflight_at_arrival True`, catalogue = the stale list).
- Revision-2 pins updated for (B): A1-unit is "one loss → no re-request → visible stop"; A2-seed's
  post-batch-40 state is `inflight True, requested True` (no retry rule); A2-exit/A2-reentry read
  `request_epoch None` at arrival (settled by the exit); the ledger row gains `settled`.
- Existing tests that now move (measured under the shadow, `<scratchpad>/probe_r3b_tests.py`, 267
  tests of 9 modules): the two `tests/test_policy_town.py` tests (revision 2) plus
  `tests/test_home_knowledge_scan.py::test_missing_response_falls_back_to_existing_page_scan`
  (`:333-347`) and `::test_abandonment_allows_exactly_one_rerequest_per_home_visit` (`:398-412`) —
  both pin the deleted retry rule. Two further movers in that run
  (`test_home_light_alternation::test_pin_s_and_c_incident_trajectory`,
  `test_policy_home::test_public_calibration_restore_converges_twelve_items`) are the direct-consume
  idiom above; they are expected green once `consume_home_knowledge` settles — **UNVERIFIED**, see
  the list at the end. The HEAD baseline of the same 267-test run (finished after the spec was
  written): 0 failures, the same 4 `test_policy_home` errors (sandbox-cwd relative paths /
  `approved_quest_strategy` None — environmental, identical in both runs), 3 skips. So exactly the
  six named tests move under the revision-3 shadow, nothing else in those 9 modules.

Designer's round-3 verification (offline, sandboxed under the scratchpad, `src/`/`tests/`
untouched; `git status --short src tests capture-ledger` unchanged; live ledger/hold sizes and
mtimes unchanged): `<scratchpad>/probe_r3b_shadow.py` (the (B) mechanism as monkeypatches:
token/settle/exit, rung gate emulated through a `_home_knowledge_scan_requested` property, retry
block emulated as deleted, dispatcher predicate + ledger) driven by `<scratchpad>/probe_r3b.py`
and `probe_r3b_p5x.py` in modes B / R2 (revision 2) / HEAD; results are quoted per pin below. Not
run this round: the CK36 seed drive under the shadow (`probe_r3b_seed.py`) and the
consume-settles re-run of the two direct-consume movers (`probe_r3b_tests2.py`).

## SUPERVISOR ADDENDUM (round 3, after the codex re-review `jsonlog/codex-review-town-owner-retired-r3.out.log` = ACCEPT WITH CHANGES, one required change)

codex's only remaining required change: *"remove the production `request_epoch is None` acceptance arm,
or explicitly clear `inflight` when migrating a checkpoint without a token. Legacy restoration can
produce `inflight=True, request_epoch=None`, so the arm can accept an uncorrelated Home response"*
(`:633-642`).

**Decision — take the second half: close the production hole at the restore point, keep the arm.**
Removing the arm would also change the mocked-chooser paths the arm exists for
(`tests/test_cli.py:781-898`, the hand-set `inflight` tests in `tests/test_home_knowledge_scan.py`),
which is a wider change than the defect needs. Instead:

- **3c-1.** In `latch_onset_capture.py:100-112`, the restore must not merely `setdefault` the two new
  attributes. Whenever `_home_knowledge_scan_epoch` is **absent** from the restored state (a legacy
  checkpoint, i.e. exactly the migration case codex names), the restore must additionally force
  `restored.__dict__["_home_knowledge_scan_inflight"] = False` — an uncorrelated pending request is
  abandoned, never accepted. A checkpoint that *does* carry the token keeps both values as saved.
- **3c-2.** The same rule applies to every other restore path that can rebuild a policy from a state
  mapping without the token, `home_entry_capture.py`'s `STATE_FIELDS` round-trip included: absent
  token ⇒ `inflight` forced False. sol must enumerate the restore paths it found and state, per path,
  that the rule is applied there.
- **3c-3.** Safety direction, stated so it is not weakened: the forced value is the REJECTING one. A
  response that really was in flight across a restore is discarded, and the next town entry re-arms
  (A1) and asks again. No response is accepted on the strength of a missing token in production.
- **3c-4.** Pin: a restore from a legacy state mapping (no `_home_knowledge_scan_epoch`) that carries
  `_home_knowledge_scan_inflight = True`, followed by a `home/9` line through the real CLI dispatcher,
  must be **REJECTED** (`accepted False`) and the catalogue unchanged. Build the legacy mapping from
  the real capture/checkpoint writer at HEAD (it predates the token by construction), not by deleting a
  key from a revision-3 mapping by hand. Lone revert: without 3c-1 the same line is ACCEPTED.

Everything else in revision 3 is confirmed by codex r3 and stands unchanged: option (B) is forced
(no request identity is emitted), the FIFO soundness argument holds, settlement is complete with no
cross-visit absorbing state, `observe_scan_refused` leaves no enterable latch, the
`consume_home_knowledge` split is correct, and A2-supersede drives the real consumer with a real
invalidation. The four UNVERIFIED groups are accepted as implementer checks — sol must make the named
real-hunk modules and the two direct-consume tests pass before claiming acceptance.

**Q4 (codex r3 item 3) — ANSWERED BY THE USER 2026-09-12, 「現行案のまま承認」, LOCKED.** Deleting the
board-based retry (`policy.py:3153-3165`) is required — it declares loss prematurely — and no settlement
event exists for a genuinely lost response before the visit ends, so under (B) **ONE** lost response
ends that visit's Home-first attempts and reaches the visible `town:blocked:owner-retired`; the next
visit re-arms (A1) and asks again. The locked Q2 answer was phrased for TWO losses; the user was shown
that this becomes one and approved it as the final shape. Do NOT add a retry, a counter or a timeout to
soften it, and do NOT retire the purchase claim. Acceptance must state this one-loss consequence
explicitly. (Rejected alternatives, recorded: an exit→re-entry re-acquisition — deferred, would need its
own oscillation-safe design; and gating the decision on measured live loss frequency — the decision was
taken now instead.)

---

## Revision 2 changelog (designer, 2026-09-12 round 2, after the codex spec review `jsonlog/codex-review-town-owner-retired.out.log` = ACCEPT WITH CHANGES)

Kept verbatim (codex confirmed, supervisor locked): "Standing decisions", "USER ANSWERS to Q1/Q2/Q3",
the root cause (a)(b)(c), the measured evidence, the key-queue ordering as INFERRED, the
`tests/test_cli.py:781-898` change, and the statement that Hunk A1 introduces no within-visit loop.

**Required change 1 (codex item 3) — acceptance is bound to the posting visit, at dispatch time.**
- The boolean `_home_knowledge_scan_outstanding` of revision 1 is gone. In its place: a **town-visit
  epoch** `_town_visit_epoch` (the game turn of the first in-town board line of the visit; `None`
  outside town) and a **request token** `_home_knowledge_scan_epoch` (the visit epoch copied at
  `confirm_key_posted` of `~9`). A `home/9` response is accepted iff
  `request token is not None and request token == _town_visit_epoch` at the moment the CLI dispatches
  it (or the unchanged in-flight heuristic, which in production implies the token; see A2).
- The epoch is minted/ended by ONE policy method, `observe_town_visit_epoch(in_town, turn)`, called
  from `_observe` (every decided snapshot) **and from the CLI dispatcher for every board line it walks
  before a response line** (`cli._dispatch_response_lines`). That closes codex's three windows: a
  dungeon board earlier in the same batch, a dungeon board the follow loop never decided on, and a
  re-entry board that precedes the response — all end or change the epoch before the compare.
- Hunk A1's re-arm now lives in the same method (entry branch: epoch `None` → minted) instead of the
  `_town_was_in_town` edge of `policy_observation.py:64-76`. Measured reason: with the edge form, an
  exit+re-entry that the policy never decided on (both boards in one batch, probe P2b) left
  `_town_was_in_town` True, so the next visit was never re-armed and no `~9` fired. Keyed on the
  epoch the re-arm fires whenever a visit begins, decided or not.
- Town exit also clears `_home_knowledge_scan_inflight` (the request cannot be answered in that visit
  any more). Declared consequence: a dungeon board after a lost `~9` no longer spends the retry nor
  calls `_home_errand.observe_scan_refused` (`policy.py:3156-3168` sees `inflight` False); the next
  visit's re-arm made the retry count moot anyway. Measured on the public-path fixture (probe P2a').
- Codex's smaller confirmations folded in: no death reset (policy lifetime ends on restart); a
  generic floor change does not end the epoch, town exit does; Home-mutation handling unchanged.
- Restore/telemetry: both attributes get `restore_checkpoint` setdefaults and `STATE_FIELDS` entries;
  the ledger row keeps `accepted`/`inflight_at_arrival`/`items` and adds `outstanding_at_arrival`,
  `request_epoch`, `visit_epoch_at_arrival`.

**Required change 2 (codex item 5) — no seed assertion past the first hunk-caused divergence.**
- **Removed from A1-seed:** the dispatch of the recorded 2,816,126 Home list, "`_home_knowledge_current`
  True / 56 items", "the store-4 page decision is observe-and-leave", "the outside decision is
  `shop:one-shot-buy` with gate `wrapper-no-procurement-need`", "no `town:blocked:owner-retired` in the
  window". A1-seed now stops at the divergence: the first decision on the 1735 snapshot is `~9`, the
  epoch is minted, the token is set by the real confirm. **Replaced by** A1-unit (public-path two-visit
  fixture, revert-proof) and A1-buy (independent public-path fixture proving "current knowledge → the
  compose is `shop:one-shot-buy`, no yield"; measured at HEAD, hunk-independent by design).
- **Removed from A2-seed:** "the next decision is not `home:request-knowledge-scan` (measured
  CK36+A2: `seek-downstairs '7'`)". A2-seed stops at the acceptance of turn 2,781,768. **Replaced by**
  A2-unit (public path: late response accepted → no second `~9`; lone revert → second `~9`).
- **Removed pin S-HEAD** (the loop rows 1744-1750 on the seed): its only remaining role, the revert
  anchor, is A1-seed's lone-revert value (`('town:restore-combat-weapon', 'wna')`, `requested` True,
  drive row 1735 at HEAD). The loop reproduction stays as designer evidence (`drive_CK1735.log`).
- **Added** A2-exit and A2-reentry (the two rejections codex demands; both drive the real CLI
  consumer with the real policy on one instance, both flip under a lone revert of A2), and
  CLI-town-helper (fidelity of the dispatcher's cheap `in_town` reading against `parse_snapshot`).
- Fixture shrinks: checkpoints at **36 and 1735** only (795/1745/1746 dropped with S-HEAD); the window
  is batches 39-44 of the run (seq 36-41: `~9`, `7`, `[knowledge, board]`, `>`, `[knowledge, board]`,
  the first dungeon boards at turn 2,781,779 = a real recorded town exit, recorder lines 7687-7697).
  The 1735-1750 window and the 2,816,126 line are no longer shipped.
- The test_cli follow test's new assertion is `outstanding_at_arrival` **False** with `request_epoch`
  None (not True as in revision 1): its mocked chooser never observes a town snapshot (`_snap_line`
  is dungeon level 1), so no visit epoch exists there and acceptance is by the in-flight path.
  `accepted True` / `inflight_at_arrival True` at `:888-889` stay untouched, as codex required.
- Two existing tests in `tests/test_policy_town.py` (`:8136-8147`, `:8149-8163`) hand-set
  `_home_knowledge_scan_requested = True` on a never-observed fresh policy to suppress the `~9` rung;
  A1's entry re-arm clears that before the rung (measured: both flip to `~9`). Revision 1's
  `_town_was_in_town`-edge form would have broken them identically (a fresh policy's first town
  snapshot is that edge) and did not list them. They must change (see "Existing tests that must
  change"); the faithful conversion is a current catalogue through the public consumer.

Designer's round-2 verification (all offline, sandboxed under the scratchpad, `src/`/`tests/` untouched;
`git status --short src tests capture-ledger` unchanged; `jsonlog/sol-events.jsonl` shows as modified
in `git status` but was not written by the designer): the proposed mechanism was shadowed in-process
(`<scratchpad>/probe_r2_epoch.py`, monkeypatches on `HengbotPolicy` and `cli._dispatch_response_lines`)
and every pin shape below was driven at HEAD and with the shadow (`--head` flag); the existing
tests named below were run in-process with the shadow (`<scratchpad>/probe_r2_tests.py`,
45 tests: `test_home_knowledge_scan`, `test_home_entry_capture`, `test_latch_onset_capture` whole,
plus the named tests of `test_cli`, `test_policy_shop`, `test_policy_quest`, `test_policy_town`):
green except the two `test_policy_town` tests above (and the test_cli follow test only because the
shadow's ledger row omitted `items`; the production row keeps it).

---

Designer: the design agent (round 1, 2026-09-12 09:00-12:30; round 2 after the codex review).
Reviewer: codex (spec review before implementation), then the user confirms (rule
`user-confirms-final-spec`). Implementer: sol. Supervisor dispatches, integrates, runs the
suites/gates, pushes.

HEAD = origin/main = `8659053`. The stopped run executed this tree (session marker
`jsonlog/bot-decisions.jsonl` 08:12:32, `git_commit 8659053`, argv with `--control-port 47820`).

## Runtime state (read before touching anything)

- **Round 2 note:** the bot AND the game are stopped on purpose and the game exe was rebuilt from
  upstream. Do not start either. `jsonlog/maintenance.hold` is set; do not touch it or the saves.
- (Round 1 state, for the artifacts' context) The bot **STOPPED** itself at 08:17:47
  (`town:blocked:owner-retired`, decision 1750, turn 2,852,686) with the character on the Alchemist
  entrance (37,91), the store-4 page open at the last snapshot.
- **Never `git reset --hard`** in this repo (`jsonlog/sol-events.jsonl` is tracked).
- **Every offline drive MUST be sandboxed and run in the foreground** (see the light-alternation
  spec's "Runtime state"). The designer's drives ran with `os.chdir(<scratch>/sandbox_retired*)`,
  `HENGBOT_HOME_HISTORY_DIR=<sandbox>`, `exploration_ledger_path=<sandbox>/exploration-ledger.json`,
  `_loadout_report_path` / `_character_calibration_path` (copy of `jsonlog/character-calibration.json`)
  / `_confirmed_loadout_path` at sandbox files, `_latch_capture_path=None`, `_home_entry_capture=None`,
  and — new for this incident — `knowledge_ledger_path=<sandbox>/knowledge-responses.jsonl` passed
  to every `cli._consume_response_sequence` call (its default is the repo's
  `capture-ledger/knowledge-responses.jsonl`, cli.py:67-69; a drive that omits it writes into the
  live ledger). Verified after every drive: `git status --short src tests jsonlog capture-ledger`
  unchanged, the four live files' sizes/mtimes unchanged. A drive that writes into the repo is a
  spec violation on its own. One full-run drive (1,750 decisions) takes ~95 s.
- The designer's harness is `<scratchpad>/drive_retired.py` (supervisor: copy it into the dispatch;
  it is the seed cutter for the fixture below). Round-2 probes: `<scratchpad>/probe_r2_epoch.py`
  (shadow of the mechanism + every pin shape, `--head` for the HEAD values) and
  `<scratchpad>/probe_r2_tests.py` (existing tests in-process under the shadow); their shadow code
  is the reference shape for the hunks, not a patch to copy.

## Standing decisions this design is bound by (verbatim where the source is verbatim)

- **Home-first procurement** (user 2026-08-18, memory `bot-home-first-procurement`): attempt Home
  withdrawal BEFORE any store purchase, universally; fall through only on fresh Home-absence
  evidence. In code the "fresh evidence" is `_home_knowledge_current`, produced by the complete
  `~9` list (`consume_home_knowledge`, `policy_home.py:235-252`, commit `3f335e3` "Make Home
  knowledge the catalogue source") or a complete open Home page (`policy.py:3461-3478`).
- **Town liveness invariant** (APPROVED 2026-08-19): in town movement is never progress; a claim
  that cannot make progress must self-retire or reach a visible terminal; the arbiter retirement
  (`town:blocked:owner-retired`, `cli.py:383/404`) is an approved visible terminal.
- **User rule (2026-09-09, Q2 ranged spec):** 「満たせない要求は可視停止で報告すること。無言のループや無限の
  買い物周回にしてはならない。」
- **Anti-enbug** (memory): no new `*_LIMIT`/counters/timeouts; state-based; revert-proof pins; the
  3-strike breaker. **Alternating-owner class**: fix by removing an owner's authority or keying
  the bound on something the loop cannot mint, never by a new detector.
- **PIN FIDELITY** (`C:\hengband\.claude\skills\bot-ops\PIN-FIDELITY.md`): real producers, one
  instance, no hand-injected state, capture-replay checkpoints are the sanctioned seed substrate
  (`tests/trajectory_harness.py:85-125,148-153,191-225`; existing `*-checkpoints.jsonl.gz`
  fixtures). Game data in tests via `find_monrace_definitions(Path(__file__), None)` /
  `find_quest_definitions(Path(__file__))`. Any new policy attribute needs a `restore_checkpoint`
  setdefault (`latch_onset_capture.py:100-112`).

## Measured evidence (designer, 2026-09-12; every number computed from artifacts)

Artifacts: `jsonlog/incident-town-owner-retired-20260912.decisions.jsonl` (1,717 rows, seq 36-1750;
seq 1-35 are in `jsonlog/bot-decisions.jsonl` at 08:12:35-08:13:06), `...snapshots.jsonl.gz`
(96 recorder lines, turns 2,850,007-2,852,686), the full recorder generation
`jsonlog/snapshots/snapshots-current.jsonl.gz` (lines 7637-9471 cover the whole run from the 08:12
resume), `jsonlog/checkpoints/policy-state.json` (written 08:17:33, i.e. after decision 1735 — the
floor-change checkpoint, `flight_recorder.py:363-368`), `capture-ledger/knowledge-responses.jsonl`
and `capture-ledger/read-batches.jsonl` (per-batch line types and posted keys, batch_seq 1-1788 of
this run), `jsonlog/bot-posted-characters.jsonl`.

### The run

One bot process from the 08:12:38 resume (a fresh `ConservativePolicy`, cli.py:2652-2663; the
08:12:35 `identify:normal 'uik'` row is the launcher's separate `--once` process). 1,750 decided
batches. Three town passes:

```
08:12  seq   1- 35  Home scan (~9 accepted at 2779969/2780011), Home deposit/withdraw (pd5 = 5 財宝感知), General, Alchemist,
                    Home withdraw, Weapon, travel to the entrance; seq 36/38 ~9 at (31,150) [both REJECTED], 39/40 descend
08:14  seq 780-799  Home page (equipment-transaction), General, Weapon observed; 795/797 ~9 at (31,150) [both REJECTED], descend
08:17  seq 1735-1750  arrival by '<' (fundraise:ascend), destroy x2, restore weapon, travel to the Alchemist, then the loop below
```

Rows 800-1734 (936 rows) are all dungeon rows (`fundraise` 875, `melee` 32, `ranged` 22, …): no Home
or store operation between the 08:14 `~9` and the 08:17 arrival, so the Home list of turn
2,816,126 (56 items, 財宝感知の巻物 ×1) is the Home content at 08:17.

### The loop (decision rows 1742-1750, all fields from the rows)

```
seq  turn     pos     st  reason / key                                        store_visit                         arbiter (producer, progress, remaining, retirement_set)  home_gate branch / composition_refusal
1742 2852087 (31,150) -   shop:travel '\x1b`n%.'                              town-errand 4 entering opened 1742  store-router True 8 []                                -
1743 2852087 (31,150) -   store:entry-await-observation ''                     same                                store-router False 7 []                               -
1744 2852640 (37,91)  4   town-progress-invariant:continue-observed-shop '\x1b' same, leaving                      detectors True 2 []                                   evaluate-stale-current-visit
1745 2852651 (37,91)  -   shop:approach '7'                                    town-errand 4 approaching opened 1745 (granted-new)  store-router True 8 []             wrapper-yield-current-visit / shop:home-first-yields-to-current-visit (seq 1745)
1746 2852662 (36,90)  -   shop:approach '3'                                    same, entering (granted-existing)   store-router True 8 []                                -
1747 2852662 (37,91)  4   town-progress-invariant:continue-observed-shop '\x1b' same, leaving                      detectors False 0 ['detectors'] would_retire          evaluate-stale-current-visit
1748 2852674 (37,91)  -   shop:approach '7'                                    town-errand 4 approaching opened 1748 (granted-new)  store-router False 0 ['store-router'] wrapper-yield-current-visit / …yields-to-current-visit (seq 1748)
1749 2852686 (36,90)  -   shop:approach '3'                                    same, entering                      store-router True 8 []                                -
1750 2852686 (37,91)  4   town:blocked:owner-retired '5'                       same, leaving                       town-plan False 2 []                                  evaluate-stale-current-visit
```

Constant on every row: gold 18,396; `procurement_requirements` = *Identify* source 0/1, Quest
launcher ammunition 81/99, Quest Light scrolls 0/1; `town_plan {stops [Alchemist, General Store],
index 0}` (index 0 on 1745 and 1748 too, i.e. after the yield of the same decision);
`shop_selector.wanted_purchase` = 財宝感知の巻物 letter q price 23 count 31, `rejection_reason
"preempted"`; `home_gate.inputs = {knowledge_current: false, knowledge_invalidated: true, attempted:
false, blocked_store: false, approach_fails: 0}`, `candidate: null`; `_town_store_attempted {}`
(checkpoint). The Alchemist shelf (recorder line 87, 21 items) holds q 財宝感知の巻物 ×31 @23, n/o
光の巻物 ×29 @23 / ×10 @12, j 鑑定の巻物 ×99 @78 — no *Identify*. The pack (line 86) holds
財宝感知の巻物 ×3, two Staffs of Identify, no Light scroll.

### The checkpoint (policy-state.json, 08:17:33 = pre-decision 1736 state)

`_home_knowledge_current false`, `_home_knowledge_valid_before 3`, **`_home_knowledge_scan_requested
true`**, `_home_latch_active {home-capture-complete, 2780011}`, `_town_store_attempted {}`,
`_town_errand_plan null`, `_home_visit {state approaching, request deposit/home-deposit 油つぼ ×5}`,
`_town_store_positions[7] [[45,123]]`, `_fundraising_mode "mine"`.

### The `~9` ledger (capture-ledger/knowledge-responses.jsonl) and the posted-character order

```
turn     time      items accepted inflight_at_arrival   where posted
2779969  08:12:43   55   True     True                  (45,124) after the Home step-off
2780011  08:12:51   56   True     True                  (44,124)
2781768  08:13:07   56   False    False                 (31,150) seq 36
2781778  08:13:09   56   False    False                 (32,151) seq 38
2816110  08:14:55   56   False    False                 (31,150) seq 795
2816126  08:14:57   56   False    False                 (32,151) seq 797
```

Posted characters (`bot-posted-characters.jsonl`): `\x14` (the travel-entrance macro, seq 34)
08:13:05.256 → `3` (seq 35 `seek-downstairs`, same turn 2,781,166 as the macro) 08:13:06.468 →
`~ 9 ESC ESC` (seq 36) 08:13:06.971 → `7` (seq 37) → `~ 9 ESC ESC` (seq 38) → `> \r y` (seq 39).
Identical shape at 08:14:53-57 (seq 793-798). Recorder order after seq 36: `player_turn 2781768 at
(32,151)` (the character moved SE = the queued `3`), then `knowledge 2781768`, then `player_turn`.

Read batches of the seq 36-41 window (`read-batches.jsonl` batch_seq 39-44; recorder lines
7687-7697, all with `floor.in_town` present):

```
batch  lines (type turn)                                   decided  posted      seq
39     player_turn 2781757                                 yes      ~9 ESC ESC  36   floor in_town true
40     player_turn 2781768                                 yes      7           37
41     knowledge 2781768, player_turn 2781768              yes      ~9 ESC ESC  38   the late response, rejected at HEAD
42     player_turn 2781778                                 yes      > \r y      39
43     knowledge 2781778, player_turn 2781778              yes      (dup)       40   still in town (the > had not executed)
44     player_turn 2781779 ×3                              yes      fm4         41   dungeon 2 level 1, in_town false — a real recorded town exit
```

### The arbiter accounting (drive trace; `town_arbiter.py:281-284, 329-341, 372-379`)

`(detectors, durable-vector)` recurs at 1744 (count 1) and 1747 (count 2 = `TOWN_CYCLE_BREAK_LIMIT`,
`policy_constants.py:227`) → `would_retire`, `_retired['detectors']`; at 1750 `may_select(
"town-progress-invariant:continue-observed-shop")` is False (`:376-379`), `owner_for_reason` =
`detectors`, `_arbiter_close_store_visit` is a no-op (visit owner `town-errand`), the supplier
counterfactual is skipped because `snapshot.store is not None` (`policy.py:2389-2399`) →
`town:blocked:owner-retired` WAIT (`:2419-2421`) → `POLICY_FINAL_STOP_REASONS` (`cli.py:383`) →
stop. `store-router` was retired at 1748 and un-retired at 1749 because its vector carries the goal
distance (`policy_town.py:106-111`); the detectors vector is durable and unchanged.

### Offline reproduction on a fresh CLI-shaped policy (seed provenance, pre-registered)

Harness `<scratchpad>/drive_retired.py`: `ConservativePolicy` built exactly as `cli.py:2462-2663`
(monrace/baseitem/terrain/Outpost + towns 2-5/wilderness/dungeon/quest knowledge/strategies),
`_prompt_gated_posting=False` (declared deviation: live had a control client; no identify chain
occurs in the town rows), primed on recorder line 7638 (turn 2,779,937, the line the long-lived
process primed on), then every `read-batches.jsonl` row of the run replayed in order against
recorder lines 7639-9471 (1,833 lines, 0 alignment mismatches): each batch is dispatched through
`cli._consume_response_sequence` (real knowledge/character/look consumption), a decided batch's
newest snapshot goes through `choose_key` → `_record_atomic_home_page` → `validate_read_key` →
`cli._send_new_decision_key` (real `PostingContract`, duplicate-key suppression, refusal →
`refuse_key_posting` → re-decide) → `confirm_key_posted` when sent. Result at HEAD:

```
decided 1750, (reason,key) == live on 1706 rows; rows 36-40, 780-799, 1744-1750 equal 1:1;
FINAL STOP town:blocked:owner-retired at seq 1750 turn 2852686;
knowledge ledger in the sandbox: 2779969/2780011 accepted, 2781768/2781778/2816110/2816126 rejected (inflight_at_arrival False) — identical to live;
state at 1746: scan_requested True, scan_retries 0, knowledge_current False, invalidated True, probe None, plan ([4,0],0),
                visit town-errand/4/entering opened 1745, composition_refusal shop:home-first-yields-to-current-visit.
```

The 44 non-matching rows are the CLI-timer `periodic:*` rows (no wall clock in the drive), walking
vs native-travel choices that follow them (1735-1743), and one step-off direction at seq 5. Rows
1735-1743 differ only there; at 1744 the drive re-converges and stays 1:1 through the stop. The
drive's visit owner at 1742-1744 is `equipment-transaction` (transferred) where live's is
`town-errand`; from 1745 (`home-first-yield` close + re-acquire) both are `town-errand`. The drive's
row 1735 at HEAD is `('town:restore-combat-weapon', 'wna')` with `requested True, inflight False,
retries 0` (`drive_CK1735.log`; live's 1735 row is the CLI-timer `periodic:game-save`).

Pre-decision checkpoints (`latch_onset_capture.checkpoint`, 8.3 MB b64 ≈ 550 KB gz each) were
dumped at 36, 795, 1735, 1744, 1745, 1746. Restoring `pre1735` and replaying the 54 recorded lines
from batch 1774 on (6 s) reproduces rows 1744-1750 and the stop 1:1 (`drive_CK1735.log`);
restoring `pre36` and replaying to the end reproduces the whole run (1706/1715 matches, stop at
1750).

### Shadow drives (monkeypatched on the harness instance; `src/` untouched)

```
variant                  what                                                                       result
A1 (full run)            reset scan bookkeeping at the town-visit epoch boundary                   1735 posts ~9; the recorded stream has no response (live never posted ~9 there) → retry burned on live's boards → HEAD loop and stop again. REPLAY ARTEFACT, not evidence.
CK1735 + A1 + R          same, and the drive's ~9 is answered with the recorded 2816126 Home list  1735 '~9' (requested False before, True/inflight after) → current True → 1744 store page: gate evaluate-no-procurement-need →
                         (R = stand-in for the response the game would emit; content justified     1745 outside: `shop:one-shot-buy '5'` (gate wrapper-no-procurement-need, visit shop-one-shot/4) → 1747 page: 'pq5\r\r\x1b'.
                         above: no Home operation between 08:14 and 08:17)                           Rows after 1735 run on live's boards (NOT authentic — codex item 5); designer evidence only, no pin asserts them.
CK36 + A2                accept a home/9 response while a scan is outstanding and knowledge is    2781768 accepted → current True at 37; 38 is `seek-downstairs '7'` (live: a second ~9); the later stop at 797 is
                         not current (the CLI predicate change), tracked by a harness-side fact    the drive's `descend` on live's boards (departure recurrence) — replay artefact past the first divergence.
```

### Round-2 shadow of the epoch mechanism on public-path fixtures (`probe_r2_epoch.py`; SHADOW vs `--head`)

Fixture `tests/test_home_knowledge_scan.py::town_with_home()` (turn 542,954, town_flag True),
`dungeon = replace(town, town_flag=False, floor_key=(1,1,0), turn+10)`, `town2 = replace(town, turn+20)`;
board lines carry `floor {dungeon_id, level, in_town}`; responses are `home_response()` lines.

```
probe  shape                                                                 SHADOW (proposed)                                              HEAD
P1     ~9, abandon, ~9, abandon (one visit) → dungeon → town2                visit#1 after 2 losses: ('town:blocked:owner-retired','5');    same terminal in visit#1; dungeon: epoch ABSENT;
                                                                             dungeon: epoch None; town2: ('home:request-knowledge-scan',   town2: ('explore','6') — no ~9 (the latch)
                                                                             '~9\x1b\x1b'), epoch 542974, retries 1
P2a    ~9 confirmed; ONE batch [dungeon board, knowledge]                    accepted False, visit_epoch_at_arrival None, request_epoch    accepted True (inflight True) — the codex window
                                                                             542954, inflight False, current False
P2a'   ~9 confirmed; dungeon decided; then [knowledge]                       rejected (epoch None); retry NOT spent (retries 1)             rejected (retry rule; retries 0)
P2b    ~9 confirmed; ONE batch [dungeon, town2 board, knowledge]             accepted False, visit 542974 ≠ request 542954; then           accepted True; town2 decision ('explore','6')
                                                                             choose_key(town2) → '~9' (re-armed by the dispatcher's mint)
P2c    ~9 confirmed; board decided (retry rule: inflight False, requested    accepted True (outstanding True, inflight False), current      accepted False; next decision '~9' (= live seq 38)
       False, retries 0); then [knowledge]; next decision                    True; next decision ('explore','6') — no second ~9
P2d    never posted; [knowledge]                                             rejected, request_epoch None                                    rejected
P2e    tks:263 shape (inflight by hand, floorless boards) / test_cli shape   both accepted via inflight; outstanding False, request None    both accepted
P4     legacy pickle (attributes absent) → setdefault None → in town         first decision mints 542955 and posts '~9'; response accepted  same decision; accepted (inflight)
P3     test_policy_shop.py:6973 fixture, knowledge current via              ('…=>shop:one-shot-buy','5'), refusal None, operation_key      identical (consumer outcome, hunk-independent)
       consume_home_knowledge(()) instead of stale                           'pa99\r\r\x1b', next 'shop:one-shot-in-flight'; stale: yield
```

## Root cause (a)(b)(c); MEASURED vs INFERRED

**The loop has two owners and no satisfier.** The purchase is wanted and affordable (18,396 gold vs
23), but every compose is refused by the Home-first gate's *stale-knowledge* branch, and nothing in
the state can make the knowledge current.

(a) **Why `continue-observed-shop` fires from the store page** — MEASURED (rows 1744/1747/1750
`town_progress_invariant.winning_rung shop:observe-and-leave`, `progress_action …continue-observed-
shop`), code: the in-store handler never buys, it records the page and leaves
(`policy.py:4171-4176`, `shop:observe-and-leave`); `_town_procurement_decision` relabels that leave
to `town-progress-invariant:continue-observed-shop` whenever `_town_observed_purchase_is_composable`
(`policy_town.py:553-565`, `:456-465` — gold and reserve only, the Home gate is not consulted).
The purchase is then composed outside, on the entrance, by the one-shot path
(`policy.py:3342-3383` acquires a `shop-one-shot` visit and calls `_atomic_shop_transaction_key`,
`policy_shop.py:3768-3862`).

(b) **Why the approach is re-armed with a NEW visit** — MEASURED (rows 1745/1748: `composition_refusal
shop:home-first-yields-to-current-visit` with `composition_refusal_sequence` = the same decision,
`home_gate.branch wrapper-yield-current-visit`, `candidate null`, `knowledge_current false`; then
`store_visit town-errand/4 opened 1745|1748 acquire granted-new`, `town_plan.index 0`). Code:
`_shop` → `_purchase_has_fresh_home_absence` (`policy_shop.py:1130-1177`): `not
_home_knowledge_current` (`:1139`) → Home exists and is available → `filed =
_ensure_home_visit_request` True (`:1157`; `_home_visit.file` returns "active" for the standing
deposit request, `home_visit.py:106-108,131-149`) → the open visit is the one-shot visit for store 4
(`:1151`, always the case on this path because `policy.py:3363` opened it one call earlier) →
`_home_procurement_probe = None` (`:1163`) → HOME_FIRST "wrapper-yield-current-visit" (`:1167`) →
`_shop` returns `shop:home-first-before-purchase` LEAVE (`:3238-3242`) → `_atomic_shop_transaction_key`
takes the yield branch (`:3847-3862`): `plan.index += 1`, `_close_store_visit("home-first-yield")`,
`return None` → `_decide` (`policy.py:3381-3383`) → the errand rung (`policy.py:5089-5093`) →
`_shopping_approach_step` → `_next_required_store_type` **rebuilds the plan** (`policy_shop.py:721-726`,
"a disposable ordering view") → `[4, 0]` index 0 → returns 4 (`:755-756`; `_town_store_attempted`
is empty) → `acquire_store_visit` grants a new `town-errand` visit (`:3456-3474`) → entrance
step-off `7` / step-on `3` (`:3504-3513`) → the page again. The two things the yield branch relies
on are inert: the plan-index advance is rebuilt away (MEASURED: index 0 on 1745/1748), and the
nulled probe means no `procurement-home-first` Home need exists (`policy_town.py:1301-1306`; and
`:1294-1299` would clear the probe anyway because the pack already holds the class). No Home stop
ever enters the plan (`town_plan.stops [Alchemist, General Store]` on every row).

(c) **Why the only satisfier is dead** — the `~9` rung (`policy.py:3124-3155`) is the mechanism that
turns stale knowledge into current knowledge without a walk (it fired at exactly this step-off cell
(36,90) on 2026-09-10 18:17:09, `bot-decisions.jsonl.1` seq 12, after which the buy composed at
seq 16-18). It is gated by `not self._home_knowledge_scan_requested` (`:3147`). MEASURED:
`_home_knowledge_scan_requested = true` in the 08:17:33 checkpoint; the drive trace shows it set
True by seq 38 (`confirm_key_posted`, `policy.py:7082-7085`), never reset afterwards (`retries 0`
from 37 on), through the 08:14 and 08:17 arrivals. The retry rule (`policy.py:3156-3168`) treats
the first board snapshot after the post as "the response did not arrive": it clears `inflight`,
spends the single retry and re-arms `requested=False` once; after the second post it calls
`observe_scan_refused` and leaves `requested=True` with no reset except a fresh Home page
(`policy.py:3068-3071`) or `_invalidate_home_observation` (`policy_home.py:1679-1680`). The CLI
accepts a `home/9` knowledge line only while `_home_knowledge_scan_inflight` is True
(`cli.py:3957-3963`); the four responses arrived one batch after that flag had been cleared and were
rejected (ledger: `accepted False, inflight_at_arrival False` ×4; reproduced 1:1 in the sandbox
ledger). INFERRED (from the posted-character order and the recorder order, no game-side artifact):
the board that pre-empted each response was the result of the `seek-downstairs '3'` posted 0.5 s
before the `~9` at the same turn as the travel macro (a re-decision on an unchanged board while the
native travel ran); the game executed the queued `3` (SE move to (32,151), +11 game turns) before
the `~9` menu, so `player_turn 2781768` reached the CLI a batch before `knowledge 2781768`.
Decisive check if the supervisor wants one: the game's key queue is not logged; the recorder order
is the only witness and it is consistent 4/4 (codex: `io/input-key-acceptor.cpp:191-290` consumes
the queue in order but logs nothing; stays INFERRED).

**Class:** alternating owners (the one-shot compose refusing under Home-first ↔ the errand router
re-acquiring the same stop) with an absorbing latch (`_home_knowledge_scan_requested`) as the reason
the cycle never exits — the town-liveness class; the arbiter's recurrence budget is what makes it
visible.

### Relation to prior work

- **Not the 2026-09-11 town-stall fix resurfacing** (`8ea0f51` "Fix town ammo retention and store
  approach accounting", `390361c`, both ancestors of HEAD): those closed the `_is_oscillating`
  supplier latch and ammo retention; here `_town_store_attempted {}`, `approach_fails 0`, no
  `shopping-stuck`, and the ammo requirement is untouched. **Neighbouring** defect in the same
  family (Home-first gate / one-shot compose / errand router).
- **The two 2026-09-10 stops** (turn 2,282,433 18:17:20 store 4; 2,286,054 19:47:17 stores 3/2)
  end with the same label and owner but by a different mechanism: a posted `shop:one-shot-buy`
  whose effect never arrives (`shop:one-shot-in-flight` ×N, gold unchanged) → `shop-buy`
  recurrence → retirement. The 18:17 run's rows 10-18 show today's yield path resolving by the
  `~9` at the step-off cell. That "posted buy does not land" class predates the identify-first
  work and is **not** addressed here (Out of scope, Q3 — filed as a separate task by the supervisor).

## Is the stop itself correct? Is the purchase reachable?

- The stop is the approved liveness terminal and fired correctly (two recurrences of the same
  no-progress detector decision with an unchanged durable vector). Nothing here widens a budget.
- The purchase is reachable: gold 18,396 ≥ 23, shelf q ×31 (and Light scrolls for the 0/1 Q2
  requirement), Home at (45,123) reachable (entered at 08:12 and 08:14), and the `~9` list is
  obtainable from any town cell. The claim is fulfillable, so self-retirement/departure is the wrong
  outcome; the correct behaviour under Home-first is: obtain fresh Home knowledge (`~9`), then
  withdraw the Home stack if it satisfies the need, else buy. Designer evidence with fresh knowledge
  (CK1735+A1+R, post-divergence rows, not a pin): the gate returns ALLOW_PURCHASE
  `wrapper-no-procurement-need` (the pack's 3 scrolls already satisfy the procurement need; the
  wanted q ×5 is the selector's top-up) and the one-shot buy `pq5` composes — the same outcome the
  live 08:12 pass reached after its Home visit. The pinned form of that claim is A1-buy below.

## WHAT TO BUILD (two production hunks; no new constant, counter or timeout; two new value facts)

Contract:

> A Home-scan request belongs to the town visit in which it was posted. A visit is identified by
> the game turn of its first in-town board line (`_town_visit_epoch`); it ends at the first
> non-town board line. A posted `~9` carries its visit's identity (`_home_knowledge_scan_epoch`)
> **until it is settled**: by the first `home/9` line the CLI dispatches while that identity equals
> the visit being read (accepted if the request is still in flight, discarded if a Home mutation
> superseded it — either way settled), or by the visit's end. **While a request is unsettled no
> second `~9` is posted** (revision 3, option (B)); the CLI accepts a `home/9` response iff the
> request is in flight and its identity equals the visit the CLI is reading **at the moment it
> dispatches the line** — decided or not — so a response can never be accepted after its visit
> ended, nor before a later visit has been observed, nor after a Home mutation that followed its
> request. A new visit re-arms the request bookkeeping exactly as a fresh Home page does.

### The visit epoch — one method, two callers (shared by A1 and A2)

`policy_observation.py`, immediately before `_observe` (`:41`):

```python
def observe_town_visit_epoch(self, in_town: bool, turn: int) -> None:
    """Mint the town-visit identity on entry, end it on exit (see SOL-TASK-town-owner-retired)."""
    if not in_town:
        self._town_visit_epoch = None                     # A1: the visit ended
        self.settle_home_knowledge_request()              # A2 (rev 3): token None, inflight False —
                                                          #   no response can belong to it now
    elif self._town_visit_epoch is None:
        self._town_visit_epoch = turn                     # A1: the visit begins
        self._home_knowledge_scan_requested = False       # A1: re-arm, verbatim policy.py:3068-3071
        self._home_knowledge_scan_retries_remaining = 1   #     minus `inflight` (exit already ended it;
        self._home_knowledge_scan_leave_turn = None       #     a mid-visit restore keeps a genuine one)
```

Caller 1 (policy): `_observe`, `policy_observation.py:64`, as the first statement before the
existing `if snapshot.in_town and not self._town_was_in_town:` block:
`self.observe_town_visit_epoch(snapshot.in_town, snapshot.turn)`. The existing edge block
(`TownVisitLedger`, `_home_visit.reset_epoch()`, …, `:65-75`) is **not** modified. `prime()`
(`policy.py:3853-3865`) reaches it through `_observe`.

Caller 2 (CLI): `_dispatch_response_lines`, `cli.py:3935-4002`, for every **board** line it walks,
in order, before it reaches a response line — see A2 step 4.

Constructor (`policy.py:1542`, beside `_town_was_in_town`): `self._town_visit_epoch: int | None = None`.

The identity is a recorded game turn, not a counter: two visits cannot share one (the turn is
monotonic across a policy lifetime, and every visit boundary passes through at least one non-town
board line — a descent, recall, `<`, or wilderness step). A `None` epoch while in town (fresh policy,
legacy checkpoint restored mid-visit) mints on the next observed in-town line; a mid-visit legacy
restore therefore re-arms once (declared, harmless: pre36 has `requested False` anyway).

### Hunk A1 — a new town visit re-arms the scan-request bookkeeping

= the three re-arm statements in the entry branch above (`requested`, `retries`, `leave_turn`) plus
the `_town_visit_epoch` mint/end and Caller 1. Nothing else changes in A1: the `~9` rung
(`policy.py:3124-3155`) and its entrance-cell gate stay as they are (A2 adds one conjunct to the
rung and deletes the retry rule `:3156-3168`, see below; the per-visit "exactly one re-request"
behaviour of `tests/test_home_knowledge_scan.py:398-412` is therefore gone).
Consequence on the seed: at 1735 (`_town_was_in_town` False, `_town_visit_epoch` absent → None) the
first in-town `_observe` mints 2,852,063 and re-arms; the rung fires (`~9`). Measured on the public
fixture: P1 (`town2 → ~9`; HEAD `explore`).

Codex item 2 stands: the entry branch executes once per visit (epoch None → value); with A2 the
rung allows exactly ONE unsettled request per visit; store-entrance cells stay excluded
(`policy.py:3134-3138`). Under Q2, a lost response in a visit still ends in the visible
`town:blocked:owner-retired` (measured on the public fixture under the revision-3 shadow, P1
visit#1: `explore` ×4 then `('town:blocked:owner-retired','5')`) and does not retire the purchase
claim; the next visit asks again (P1 town#2 → `~9`).

### Hunk A2 — one unsettled `~9` per visit; a response is accepted iff it is in flight and its visit is the one being read

(Revision 3 rewrote steps 2-4 and added 2a-2c; step 1, the walk of step 4 and step 5 are revision
2's. The lifecycle: **mint at confirm → pending → settled**; superseded = pending with
`inflight False`.)

1. `policy.py:1998` (beside `_home_knowledge_scan_retries_remaining = 1`):
   `self._home_knowledge_scan_epoch: int | None = None` — the request token.
2. **Mint the token** — `confirm_key_posted`, `policy.py:7082-7085`, next to `requested`/`inflight`:
   `self._home_knowledge_scan_epoch = self._town_visit_epoch`. (In production the rung only fires on
   an in-town decided snapshot, so the epoch is never None here; if it is — a mocked chooser — the
   token is None and only the in-flight path can accept.)
2a. **Settle** — new method `settle_home_knowledge_request(self) -> None` in `policy_home.py`
   beside `consume_home_knowledge` (`:235`): `self._home_knowledge_scan_epoch = None;
   self._home_knowledge_scan_inflight = False`. It is the ONLY clearer of the token, called from
   three places: (i) the dispatcher, step 4, after any `home/9` line walked while
   `request_epoch == visit_epoch` (accepted or discarded); (ii) `consume_home_knowledge` (the `~9`
   acceptance — so tests and the dispatcher that call it directly settle too); (iii) the exit
   branch of `observe_town_visit_epoch` (a response cannot be accepted after its visit ended and
   cannot arrive after the next visit's first board — see "Soundness" in the changelog).
   **Nothing else clears it**: not `_invalidate_home_observation` (`policy_home.py:1663-1683` —
   revision 2's clear there is withdrawn; it keeps clearing `requested`/`inflight` at `:1679-1680`),
   not the fresh-Home-page re-arm (`policy.py:3068-3071`, which keeps clearing `inflight`), not the
   entry re-arm.
   The fresh-Home-page re-arm (`policy.py:3068-3073`) clears `requested`/`inflight` but not the token, so after an open-page adoption (`_adopt_home_catalogue`, `policy.py:3462`, which deliberately does not settle) that re-arm cannot produce a second `~9` for the rest of the visit: this is the LOCKED "superseded = token set ∧ inflight False" rule applying to the page path, not an oversight; the pending response settles on arrival or at visit exit, so no state is absorbing.
2b. **Split the consumer** — `consume_home_knowledge` (`policy_home.py:235-252`) becomes
   `_adopt_home_catalogue(items)` (its current body, `:237-251`, unchanged) plus a thin
   `consume_home_knowledge(items)`: `self._adopt_home_catalogue(items); self._home_scan_source =
   "~9"; self.settle_home_knowledge_request(); return True`. The open-page path `policy.py:3472`
   calls `self._adopt_home_catalogue(...)` instead (its `:3476` source override stays), so an
   observed complete page — a competing knowledge source — never settles a pending `~9`; the pending
   response is then superseded by the page's `inflight = False` (`:248` inside the adopter) and is
   discarded on arrival. (Measured under the shadow, P5x: page(1) → `home:scan-complete-from-open-
   page`, `inflight False`, token kept.)
2c. **Gate the rung and delete the retry rule** — `policy.py:3124-3155`: add
   `and self._home_knowledge_scan_epoch is None` beside `:3147` (`not self._home_knowledge_scan_
   requested`). Delete `policy.py:3156-3168` entirely (the `if self._home_knowledge_scan_inflight:`
   block: clearing `inflight` on an ordinary board, the retry decrement, the `requested = False`
   re-arm and the `observe_scan_refused("knowledge-response-missing")` call). `_home_knowledge_scan_
   retries_remaining` keeps its constructor (`:1998`), fresh-page (`:3070`) and entry re-arm writes
   (write-only vestige; declared). `inflight` is now cleared only by the adopter (`:248`),
   `_invalidate_home_observation` (`:1680`), the fresh-page re-arm (`:3069`) and settlement.
3. **Which states exist** (no new attribute beyond revision 2's two):
   `token None` = no unsettled request (the rung may fire if knowledge is stale);
   `token set ∧ inflight True` = pending, acceptable;
   `token set ∧ inflight False` = pending but superseded (a mutation or a fresh page followed the
   request) — the rung stays blocked, the arriving response is discarded and settles.
   In production `inflight ⇒ token set` (confirm sets both) and `inflight ⇒ token == visit` (exit
   clears both; a new visit mints a new epoch only after the exit).
4. **Walk and compare** — `cli._dispatch_response_lines` (`cli.py:3935-4002`):
   - board lines: at `:3950-3951` (`if response_type not in {"knowledge","look","character"}: continue`)
     call, before the `continue`, `policy.observe_town_visit_epoch(_decoded_board_in_town(data),
     int(data.get("turn", 0)))` (guarded with `getattr(policy, "observe_town_visit_epoch", None)` in
     the style of the surrounding `getattr` calls). New module helper `_decoded_board_in_town(data)`
     beside `_decode_response_lines` (`:3848`): `floor = data.get("floor") or {}`; if `"in_town" in
     floor` return `bool(floor["in_town"])`, else `int(floor.get("dungeon_id", 0)) == 0 and
     int(floor.get("level", 0)) == 0` — the same two rules as `Snapshot.in_town` (`model.py:811-818`)
     over `parse_snapshot`'s floor reading (`model.py:941, 1137-1141, 1263-1265`); no `parse_snapshot`
     call (no monrace knowledge in this function, and no grids are needed). Board-line classification
     is the one `_snapshot_entries_in_order` uses (`:3782`): everything that is not a response type.
   - response lines, `:3954-3963`: keep `inflight_at_arrival`; add
     `request_epoch = getattr(policy, "_home_knowledge_scan_epoch", None)`,
     `visit_epoch = getattr(policy, "_town_visit_epoch", None)`,
     `outstanding_at_arrival = request_epoch is not None and request_epoch == visit_epoch`,
     `is_home9 = response_type == "knowledge" and … category "home" and menu_key "9"`;
     `requested_home_knowledge = is_home9 and inflight_at_arrival and (outstanding_at_arrival or
     request_epoch is None)`. (Revision 2's `outstanding or inflight` OR is withdrawn: an
     `inflight False` response is a superseded one and must be discarded.)
   - after the existing accept/character/look branches (`:3987-4001`): `if is_home9 and
     outstanding_at_arrival: settle = getattr(policy, "settle_home_knowledge_request", None); if
     settle is not None: settle()` — the discard path's settlement (the accept path settled inside
     `consume_home_knowledge`; calling it twice is idempotent).
   - ledger row `:3967-3986`: keep every existing field (`accepted`, `inflight_at_arrival`, `items`, …);
     add `"outstanding_at_arrival"`, `"request_epoch"`, `"visit_epoch_at_arrival"`, `"settled"`
     (`is_home9 and outstanding_at_arrival`).
   Why `request_epoch is None` is accepted with `inflight`: it is HEAD's accepting path for a
   policy whose chooser never observed a town (the mocked `tests/test_cli.py:781-898` chooser,
   `_snap_line` is dungeon level 1 → confirm mints None) and for the hand-set `inflight` tests
   (`tests/test_home_knowledge_scan.py:219,233,265,306,501,511,534`); `tests/test_cli.py:888-889`
   keeps `accepted True / inflight_at_arrival True`. In production confirm always mints a non-None
   token, so acceptance there is exactly `inflight ∧ token == visit` (step 3). Measured P2e: both
   legacy shapes accepted, `outstanding False, request None`.
5. Plumbing: `latch_onset_capture.py:100-112`: `restored.__dict__.setdefault("_town_visit_epoch",
   None)` and `…setdefault("_home_knowledge_scan_epoch", None)` — **and, when the token key was
   ABSENT, force `_home_knowledge_scan_inflight = False` (SUPERVISOR ADDENDUM 3c-1/3c-2; without it a
   legacy checkpoint restores as `inflight True, token None` and the `request_epoch is None` arm of
   step 4 accepts an uncorrelated response).** `home_entry_capture.py:22-53`
   `STATE_FIELDS`: add both after `_home_knowledge_scan_leave_turn`
   (`tests/test_home_entry_capture.py:250` compares against the constant, so it stays green).
   No death reset (codex item 4): the policy object does not survive a restart.

Where the three codex windows close (all measured, P2a/P2a'/P2b):
- *after leaving town, before the first dungeon snapshot is observed*: the dungeon board precedes
  the response in the CLI stream (the game emits in order); the dispatcher walks it first →
  `_town_visit_epoch None`, `inflight False` → rejected. A response that precedes any non-town board
  line was produced in town and is legitimately that visit's list.
- *a batch containing the transition*: same walk, same batch.
- *on return to town before the first new-visit `choose_key`*: the re-entry board precedes the
  response → the dispatcher mints the new epoch → `request ≠ visit` → rejected; and the same mint
  re-arms A1, so the new visit's own `~9` fires at its first decision.
Where codex's round-2 finding closes (revision 3; measured P5/P5x under the shadow, B vs HEAD/R2):
- *request → Home invalidation → later `~9` in the same visit → delayed first response*: the later
  `~9` is not posted at all while the first is unsettled (rung conjunct, step 2c); the invalidation
  left the token and cleared `inflight`; the delayed first response is discarded
  (`accepted False, inflight_at_arrival False, outstanding_at_arrival True, settled True`), the
  catalogue keeps `current False / invalidated True / items () / count None / source None`; the
  NEXT decision posts `~9` and its response is accepted. HEAD and revision 2 both posted the second
  `~9` on the second outside decision and accepted the delayed first response (`accepted True`,
  catalogue = the stale list) — the counter-example reproduced.
- Two posts in one visit no longer exist (only one unsettled request); two responses to ONE post
  (a duplicated game-side emission) would settle on the first and be rejected on the second
  (`token None`). Not observed in any artifact (6 posts ↔ 6 rows); stated for completeness.
- A late response consumed after a Home mutation is impossible by construction: every mutation
  post/observation goes through `_invalidate_home_observation` (`policy.py:2603, 2914, 2960, 3197,
  3778`, `policy_home.py:1222, 1501, 1530, 1566, 2424`, `policy_equipment.py:1615`), which clears
  `inflight` → the response is discarded; and a mutation posted after the request executes after
  the response was emitted (FIFO), so the response is pre-mutation whenever this ordering occurs.

Hunk boundaries for the per-pin reverts: **A1** = the three re-arm statements (+ the epoch mint/end,
Caller 1, the `_town_visit_epoch` plumbing, which A2 also needs and which a lone revert of A1 keeps).
**A2** = the token (steps 1-3: mint, `settle_home_knowledge_request`, the consumer split, the rung
conjunct, the retry-rule deletion), the dispatcher walk + predicate + settlement + ledger fields
(step 4), the exit settlement, the token plumbing (step 5). A lone revert of A2 restores HEAD's
retry rule and HEAD's `inflight`-only predicate.

## Pins (PIN FIDELITY: real producers, one instance, value level, no state injection)

**Fixture** `tests/fixtures/town-owner-retired-20260912-checkpoints.jsonl.gz`, in the schema
`checkpoint_rows` reads (`decision_index`, `predecision_policy_checkpoint_pickle_b64`,
`decision_snapshot_pickle_b64`, `next_snapshot_pickle_b64`, `last_reason`, `key`,
`posted_characters`), cut by the harness from the **fresh-policy HEAD drive** (provenance above) at
decision indices **36 and 1735** (≈550 KB gz each; the pickles predate the new attributes, which is
what `restore_checkpoint`'s setdefaults are for). Companion
`tests/fixtures/town-owner-retired-20260912-window.jsonl.gz`: the `read-batches.jsonl` rows of
batch_seq **39-44** (the batch that decided seq 36 through the first batch whose lines are dungeon
boards, recorder lines 7687-7697), each row carrying its raw recorder lines in order
(`{"batch_seq", "decided", "posted_key", "lines": [...]}`). The plan event must state the
checkpoint's provenance (HEAD `8659053`, the harness, 0 alignment mismatches, 1706/1750 matches,
rows 1744-1750 1:1) and the one declared deviation of the 1735 checkpoint (visit owner
`equipment-transaction` vs live `town-errand`; the 1735 decision itself does not depend on it).

A window replay in a test = for each ledger row: `cli._consume_response_sequence(lines, policy,
send_stub, monrace, knowledge_ledger_path=<tmp>)`; if `decided`: `cli._newest_snapshot_entry` →
`choose_key` → `validate_read_key` → `cli._send_new_decision_key(... posting_contract=PostingContract())`
→ `confirm_key_posted` when sent. This is the CLI path, not a hand-built loop; do not shortcut the
dispatch (the acceptance predicate under test lives there). Game data via
`find_monrace_definitions(Path(__file__), None)` / `find_quest_definitions(Path(__file__))`; never
import `tests/test_town_stall._game_edit_dir`.

Public-path fixtures below use `tests/test_home_knowledge_scan.py`'s `town_with_home()`,
`confirm_outside_after_home_leave`, `home_response()` and the `:334-336` idiom
(`_next_required_store_type = <module-level function returning STORE_HOME>`,
`_home_processing_seen_pages.add(...)`), with `dungeon = replace(town, town_flag=False,
floor_key=(1, 1, 0), turn=town.turn + 10)`, `town2 = replace(town, turn=town.turn + 20)`, and board
lines shaped `{"type": "player_turn", "turn": T, "player": {...}, "floor": {"dungeon_id": d,
"level": l, "in_town": b}}`. Every response goes through `cli._consume_response_sequence` with a tmp
`knowledge_ledger_path`; assertions on the ledger read that file.

- **Pin A1-seed (asserts only at the divergence; lone revert of A1 flips it).** Restore `pre1735`
  (`restore_incident_checkpoint`). Assert the incident's latched state after restore:
  `_home_knowledge_scan_requested` True, `_home_knowledge_scan_retries_remaining` 0,
  `_home_knowledge_current` False, `_town_was_in_town` False, `_town_visit_epoch` None. Then the
  first `choose_key` on the 1735 decision snapshot must return
  `('home:request-knowledge-scan', '~9\x1b\x1b')` with `_town_visit_epoch == snapshot.turn`
  (2,852,063) and `_home_knowledge_scan_retries_remaining` 1 after the call; `validate_read_key` +
  `cli._send_new_decision_key(... PostingContract())` sends it; `confirm_key_posted` →
  `_home_knowledge_scan_epoch == 2,852,063`, `requested`/`inflight` True. **Nothing beyond this
  decision is asserted** (every later board in the recording follows live's non-`~9` keys). Lone
  revert of A1 → `('town:restore-combat-weapon', 'wna')` (the HEAD drive's row 1735,
  `drive_CK1735.log`), `requested` stays True.
- **Pin A1-unit (public path, fresh policy, two visits; lone revert of A1 flips it).** Post `~9`,
  confirm; then decide on the same town board until the reason starts with `town:blocked` (bounded
  by the loop, at most 8 calls): no decision in between is `~9` (the request stays pending,
  `inflight True`, `requested True`, token == town.turn) and the terminal is
  `('town:blocked:owner-retired', '5')` — the Q2 visible terminal for ONE lost response, measured
  under the revision-3 shadow (`explore` ×4, stop on the 5th call). Then `choose_key(dungeon)` →
  `_town_visit_epoch` None, token None, `inflight` False; `choose_key(town2)` →
  `('home:request-knowledge-scan', '~9\x1b\x1b')`, `_town_visit_epoch == town2.turn`. Lone revert
  of A1 → town2 gives `('explore', '6')` (measured HEAD), `requested` stays True. (Under a lone
  revert of A2 the first visit re-posts `~9` on the 2nd call — the HEAD retry rule; A1-unit does not
  assert that.)
- **Pin A1-buy (independent public-path fixture for the downstream claim; hunk-independent).** The
  `tests/test_policy_shop.py:6973-7003` fixture (`QuestCarryVisitAbandonmentTest._q2_policy()` /
  `_q2_town()` with the Weapon-store and Home grids, the errand plan, the LEAVING `town-errand`
  visit and the bolts page — the existing yield pin's own seed) with Home knowledge made current
  through the real consumer, `policy.consume_home_knowledge(())` (the method the dispatcher calls;
  used the same way by `:4353`, `:4389`, `:4535`) instead of `_home_knowledge_current = False`.
  Assert on `choose_key(outside)`: `last_reason` ends with `shop:one-shot-buy`, key `'5'`,
  `_shop_selector_diagnostics["composition_refusal"]` is None, `_store_visit.operation_key ==
  'pa99\r\r\x1b'`; the next decision is `shop:one-shot-in-flight`. Contrast in the same test: the
  stale form yields (`shop:home-first-yields-to-current-visit`, as `:7006-7009` already pins). This
  proves "fresh knowledge → the compose buys, no yield" — the claim the seed can no longer carry
  past its divergence. (Measured: gate branch here is `wrapper-fresh-catalogue-absence` — the Home is
  empty — where the seed's would be `wrapper-no-procurement-need`; the pin asserts the compose, not
  the branch name.)
- **Pin A2-seed (asserts only at the divergence; lone revert of A2 flips it).** Restore `pre36`
  (legacy pickle → both new attributes None). Replay batches 39-41 through the CLI dispatch: after
  batch 39 the decision is `('home:request-knowledge-scan', '~9\x1b\x1b')` (live), sent and confirmed
  → `_home_knowledge_scan_epoch == _town_visit_epoch` and not None (do not pin the value: the
  dispatcher mints from the first board line of the batch); after batch 40 (`[player_turn 2781768]`)
  the decision is `('seek-downstairs', '7')` (live; the rung is skipped because `requested` is True)
  and the request is still pending: `inflight True, requested True`, token unchanged (revision 3:
  no retry rule; HEAD would show `inflight False, requested False, retries 0`); after batch 41
  (`[knowledge 2781768, player_turn 2781768]`) the tmp ledger row for turn 2,781,768 has
  `accepted True, outstanding_at_arrival True, inflight_at_arrival True, settled True, request_epoch
  == visit_epoch_at_arrival`; `_home_knowledge_current` True, `_home_scan_item_count == 56`,
  `_home_knowledge_scan_epoch` None, `inflight` False. **Stop there**; the decision on batch 41's
  board is not asserted. Lone revert → `accepted False, inflight_at_arrival False`,
  `_home_knowledge_current` False (= live ledger row `:7843`). **UNVERIFIED this round**: the
  post-batch-40 `seek-downstairs '7'` under revision 3 was not re-driven (`<scratchpad>/
  probe_r3b_seed.py` is the check: `PROBE_MODE=B python probe_r3b_seed.py`, expect seq 37 `'7'`
  with `inf=True`, then the 2781768 row `accepted True`); revision 2's CK36+A2 drive and the
  HEAD trace give the same `'7'` at seq 37 with `requested True`, and the rung is the only reader
  of the flags the retry rule wrote.
- **Pin A2-unit (public path; a late response is accepted, no second `~9`; lone revert of A2 flips
  it).** Post `~9`, confirm, dispatch a board batch `[town board turn+1]` and decide on it (measured
  `('explore','6')`; `inflight True, requested True` — the request stays pending), then dispatch
  `[knowledge]` alone → ledger `accepted True, outstanding_at_arrival True, inflight_at_arrival
  True, settled True`, `_home_knowledge_current` True, `_home_scan_source '~9'`, token None; the
  next decision on a town board is not `home:request-knowledge-scan` (measured `('explore','6')`).
  Lone revert → after the board `inflight False, requested False, retries 0`, then `accepted
  False`, next decision `~9` (= live seq 38's second post; measured HEAD).
- **Pin A2-supersede (the codex pin: request → Home invalidation → NO second request → delayed
  first response rejected → catalogue keeps the post-invalidation state; lone revert of A2 flips
  it).** Real CLI consumer, real policy, one instance, `town_with_home()` + the `:334-336` idiom;
  Home-page snapshots are `replace(town, turn=…, store=StoreState(STORE_HOME, [store_item(...)×n],
  stock_num=n, page_top=0, page_size=12))` built with `tests/policy_fixtures.store_item`; between
  decisions dispatch the matching board/`store` line through `cli._consume_response_sequence`
  (tmp `knowledge_ledger_path`) so the dispatcher walks the visit. Sequence and asserted values
  (all measured under the revision-3 shadow, `probe_r3b_p5x.py` mode B):
  1. `choose_key(town)` → `~9`; confirm → token == town.turn, `inflight True`.
  2. board turn+1 → `choose_key` → not `~9` (`('explore','6')`), `inflight True`.
  3. Home page turn+2 with ONE item, complete → `choose_key` → `home:scan-complete-from-open-page`
     (`policy.py:3461-3478`, the adopter): `_home_knowledge_current True`, `_home_scan_source
     'observed-home-page'`, `inflight False`, **token unchanged** (2b).
  4. Home page turn+3 with TWO items, `stock_num 2` → `choose_key` → the count contradiction
     `policy.py:2594-2603` calls `_invalidate_home_observation` (real, public):
     `_home_knowledge_invalidated True`, `_home_knowledge_current False`, `_home_knowledge_items ()`,
     token unchanged (reason measured `home:store-context-exit`, key `'\x1b'`).
  5. outside board turn+4 → `choose_key` → not `~9` (the store-leave barrier `policy.py:3148`
     blocks this one under every revision; measured `explore`);
     outside board turn+5 → `choose_key` → **not `~9`** (the rung conjunct; measured `explore`;
     HEAD posts `~9` here).
  6. dispatch `[knowledge turn+5]` (the delayed FIRST response) → ledger `accepted False,
     inflight_at_arrival False, outstanding_at_arrival True, request_epoch == town.turn ==
     visit_epoch_at_arrival, settled True`; after it `_home_knowledge_current False`,
     `_home_knowledge_invalidated True`, `_home_knowledge_items == ()`, `_home_scan_item_count None`,
     `_home_scan_source None`, token None, `requested` False.
  7. outside board turn+6 → `choose_key` → `('home:request-knowledge-scan','~9\x1b\x1b')`; confirm;
     dispatch `[knowledge turn+6]` → `accepted True, inflight_at_arrival True, settled True`,
     `_home_knowledge_current True`, `_home_scan_source '~9'`, items 2.
  Lone revert of A2 (measured HEAD): step 5's second outside decision is `~9` (confirm it in the
  test when it is), step 6's row is `accepted True, inflight_at_arrival True` and the catalogue
  becomes `current True, items 2, source '~9'` from the STALE first response; step 7 is `explore`.
  No fixture wall: every state transition is a `choose_key`/`confirm_key_posted`/dispatcher call.
- **Pin A2-exit (rejection after a real town-exit transition; lone revert of A2 flips it).** Post
  `~9`, confirm (no decision since); dispatch ONE batch `[dungeon board (dungeon_id 1, level 1,
  in_town false), knowledge]` → ledger `accepted False, inflight_at_arrival False,
  outstanding_at_arrival False, request_epoch None, visit_epoch_at_arrival None, settled False`
  (the exit settled the token before the line); `_home_knowledge_current` False,
  `_home_knowledge_scan_inflight` False, token None. Lone revert → `accepted True,
  inflight_at_arrival True` (HEAD accepts a previous visit's list). Second assertion in the same
  test (consistency, does not flip): decide on `dungeon` first, then dispatch `[knowledge]` alone →
  rejected under both (measured: `request_epoch None` with A2).
- **Pin A2-reentry (rejection before the first observation of a later visit; lone revert of A2
  flips it).** Post `~9`, confirm; dispatch ONE batch `[dungeon board, town board (turn2, in_town
  true), knowledge]` — the whole exit and re-entry precede the response and no `choose_key` runs in
  between → ledger `accepted False, request_epoch None, visit_epoch_at_arrival == turn2, settled
  False`, `_home_knowledge_current` False; then `choose_key(town2)` → `('home:request-knowledge-
  scan', '~9\x1b\x1b')` (the dispatcher's mint re-armed A1; `requested` False before the call).
  Lone revert of A2 → `accepted True` (HEAD: `inflight` still True). (Lone revert of A1 → the final
  `~9` is absent while the rejection stands.)
- **Pin A2-control (no unsolicited acceptance).** Fresh policy that never posted `~9`, in town
  (decided once): dispatch `[knowledge]` → `_home_knowledge_current` stays False, ledger `accepted
  False, request_epoch None, visit_epoch_at_arrival == town.turn, settled False` (measured P2d).
  (Revision 2's second half is superseded by A2-supersede.)
- **Pin A2-restore.** As `tests/test_home_light_alternation.py:399-416` does for
  `_prompt_gated_posting`: a checkpoint pickled without the two attributes restores with
  `_town_visit_epoch is None` and `_home_knowledge_scan_epoch is None`; `STATE_FIELDS` contains both;
  after such a restore on a town snapshot the first decision mints the epoch and, with the `:334`
  idiom, posts `~9`, and its response is accepted (measured P4).
- **Pin CLI-town-helper (fidelity of the dispatcher's reading).** `cli._decoded_board_in_town(data)
  == parse_snapshot(data, monrace).in_town` for: every board line of the window fixture (town lines
  7687-7693 and the dungeon lines 7694-7697), a `tests/test_cli.py::_snap_line`-shaped line (level 1,
  no flag → False), a line without `floor` (→ True, the heuristic), and a wilderness line
  (`dungeon_id 0, level 0, in_town false` → False). Lone revert of A2 → the helper is absent.

If the seed cannot be driven to a point a pin needs, say so in the plan event and stop; do not
substitute a synthetic policy state or a hand-set latch.

**Existing tests that must change, and why (list each in the fix event):**
- `tests/test_cli.py::test_follow_records_batch_spans_posted_key_and_inflight_knowledge`
  (`:781-898`): its knowledge row assertions stay (`accepted True, inflight_at_arrival True` — the
  real `confirm_key_posted` runs there); add `outstanding_at_arrival` **False**, `request_epoch`
  None, `visit_epoch_at_arrival` None (the mocked chooser never observes a town; `_snap_line` is
  dungeon level 1, so the dispatcher's walk ends the epoch and the token is minted None). No other
  change.
- `tests/test_policy_town.py::TownMapNightRoutingTest::test_static_map_lets_the_bot_route_to_a_store_at_night`
  (`:8136-8147`) and `::test_posted_store_travel_without_progress_records_walking_fallback`
  (`:8149-8163`): both hand-set `_home_knowledge_scan_requested = True` on a fresh, never-observed
  policy so that the `~9` rung does not pre-empt `shop:travel`; A1's entry re-arm clears it at the
  first `_observe` and the rung fires (measured: both fail with `'~9\x1b\x1b' != '\x1b`n(.'`).
  Replace that line by `policy.consume_home_knowledge(())` (a current, complete catalogue — the rung's
  `not home_scan_complete or invalidated` condition is then False on its own, `policy.py:3139-3142`);
  the tests' subject (night routing) is untouched. Alternative if the supervisor prefers the
  smallest diff: `policy.prime(snap)` before the flag (the `:2397` idiom) — but that keeps the
  injected latch, so the consumer form is recommended.
- `tests/test_home_knowledge_scan.py::test_missing_response_falls_back_to_existing_page_scan`
  (`:333-347`) and `::test_abandonment_allows_exactly_one_rerequest_per_home_visit` (`:398-412`):
  both pin the deleted retry rule (measured under the revision-3 shadow: `:345` `inflight` is True,
  `:408` gives `'6'` not `~9`). Convert, keeping their public shape: the first becomes "a board
  after the post keeps the request pending" — after `:343` assert `inflight True`, `requested`
  True, `last_reason != 'home:request-knowledge-scan'`, token `== snapshot.turn`; the second
  becomes "no re-request while the request is unsettled" — after the abandon board assert the next
  `choose_key` is not `~9` (`:408`), `requested` True (`:411` holds), then dispatch the response
  through `cli._dispatch_response_lines` → accepted (`current True`) and the next decision is not
  `~9`. (These two conversions are A1-unit/A2-unit in the module's own idiom; keep them.)
- `tests/test_home_knowledge_scan.py` `:219-331` (hand-set `inflight`, floorless boards), `:386-396,
  414+`, `:495-544`: unchanged (measured green under the revision-3 shadow, whole module minus the
  two above).
- `tests/test_home_light_alternation.py::test_pin_s_and_c_incident_trajectory` (helper
  `_consume_response` `:121-130` calls `consume_home_knowledge` directly on `inflight`) and
  `tests/test_policy_home.py::HomeOneOperationPerEntryTest::test_public_calibration_restore_
  converges_twelve_items` (`:2229-2230`, same idiom): expected UNCHANGED because
  `consume_home_knowledge` settles (step 2b). **UNVERIFIED**: under the designer's shadow (where
  the direct call did not settle) both moved (`records[496]` `('shop:travel', …)` vs expected
  `('equipment-transaction:takeoff','tg')`; decision 111 `town:blocked:owner-retired`). The check is
  `PROBE_CONSUME_SETTLES=1 PROBE_MODE=B python <scratchpad>/probe_r3b_tests2.py` (or simply the two
  tests under the real implementation). If either still moves with the real hunks, stop and report:
  it would mean a `~9` answered while `inflight` was False at HEAD (a late response the fixture
  recorded as ignored) — a fixture-level consequence of the fix, to be re-pinned, not hidden.
- `tests/test_policy_shop.py:6973-7015`, `:2396-2406` (`prime` then the flag — safe), `:2611-2618`,
  `tests/test_policy_supply.py:3543-3639` (the yield-branch pins): unchanged (measured green).
- `tests/test_policy_quest.py:3830-3843`, `:3883-3899`: unchanged (the flag is set after a decision,
  or the rung is bypassed).
- `tests/test_home_entry_capture.py:250`, `tests/test_latch_onset_capture.py`: unchanged (measured).
- `tests/test_home_errand.py:40-44` (calls `observe_scan_refused` directly): unchanged (the method
  stays; only its production caller is deleted).
Declare any production hunk left unpinned, by name.

## Acceptance

- A1-seed and A2-seed reproduce their HEAD values under the respective lone revert (per-pin revert
  results named in the fix event) and their changed value at the divergence with the fix; neither
  asserts anything past its divergence.
- A1-unit, A2-unit, A2-supersede, A2-exit, A2-reentry flip under the named lone revert; A1-buy,
  A2-control, A2-restore, CLI-town-helper hold.
- **Q2 (binding):** a lost response in a visit still ends in `town:blocked:owner-retired`
  (A1-unit visit#1; revision 3: ONE loss suffices because no second request may be posted while
  the first can still arrive); this is the intended visible terminal, not an unfixed defect; the
  purchase claim is not retired and the bot does not depart without buying; the next visit asks
  again.
- The same-visit supersede case is closed by construction (A2-supersede) — no older response can
  become current after a Home invalidation, a fresh page, or a visit exit.
- `tests.test_home_knowledge_scan`, `tests.test_cli`, `tests.test_policy_shop`,
  `tests.test_policy_supply`, `tests.test_policy_town`, `tests.test_policy_quest`,
  `tests.test_home_entry_capture`, `tests.test_latch_onset_capture`, `tests.test_absorbing_states`
  green; the fix event states that the seed's outcome after the 1735 `~9` (the buy) is proven by
  A1-buy, not by the seed, and does not claim departure.

## Out of scope (each with its reason) and observations for the supervisor

- **The yield branch's inert hand-off** (`policy_shop.py:3847-3862`: `plan.index += 1` is rebuilt
  away by `_next_required_store_type:721-726`; the comment "the next router decision can file and
  approach the Home refresh" is false; `:1163` nulls the probe that would create the
  `procurement-home-first` need). With A1+A2 the satisfier is the `~9` rung at the step-off cell,
  which the entrance-step-off idiom always visits; the dead lines are a cleanup with no behavioural
  pin and are left alone (Q1 (a) keeps the yield's shape).
- **The duplicate re-decision behind a native travel** (rows 34/35, 793/794: `seek-downstairs '3'`
  posted 1.2 s after the travel macro at the same turn; the queued key executed after arrival). It
  caused the response race; A2 makes the race harmless. The CLI's `_duplicate_snapshot_ready` /
  travel handling is not touched.
- **`_home_errand.observe_scan_refused` → `HomeErrandState.STOPPED`** (`home_errand.py:81-84`) makes
  `_choose_key` return `home-errand:stopped` WAIT forever (`policy.py:3121-3123`) with no reset
  path visible; not hit here (`_home_errand` was IDLE on every row). Flagged as the same latch
  class. (Revision 3 deletes its only production caller with the retry rule; the method and its
  unit test stay. An errand in `NEED_KNOWLEDGE` with a lost scan now simply stays there —
  `needs_knowledge` is read only by the rung's reason label, `policy.py:3151-3154`, so no WAIT is
  introduced; the visit ends in the arbiter's visible stop under Q2.)
- **Arbiter recurrence on the departure owner**: in the replays a `descend` that does not land
  followed by another `descend` after one interleaved decision retires `departure` and stops the
  bot (`drive_CK36+A2.log` seq 797). Seen only against live's boards (artefact), never live; noted
  because the same budget (2) applies to every owner.
- **The 2026-09-10 "posted one-shot buy never lands" stops** (Q3: filed as a separate task).
- The `~9` rung's entrance-cell gate (`policy.py:3134-3138`): its rationale could not be recovered
  from history (the `git log -S` hits are moves/splits); left as is.
- `_home_knowledge_scan_leave_turn` is write-only in `src/` (`policy.py:2002, 3071, 3706`); the
  re-arm keeps resetting it for symmetry with `:3068-3071`, nothing reads it.
- `TOWN_CYCLE_BREAK_LIMIT`, the arbiter, the retry rule's single re-request, the Home-first gate's
  other branches, the identify-first work of 09-11/12.

## Process

- Append `type:"plan"` to `jsonlog/sol-events.jsonl` BEFORE implementing: pin list, per-pin seed
  provenance (checkpoint indices 36/1735, the window batches 39-44), the production hunk each lone
  revert flips, the sandbox paths every drive writes to (including `knowledge_ledger_path`).
- Run every drive in the foreground and sandboxed. Never let `cli._consume_response_sequence`
  default its ledger path.
- Commit `src/` + `tests/` + the two fixtures only. Imperative English message. **NO push.** Never
  `git reset --hard`.
- Gates (supervisor runs the suites; sol runs the named modules only): `scripts\verify_scope.py`
  (derived scope), `scripts\hunk_guard.py`, `scripts\test_fakery_lint.py`, then
  `tests.test_home_knowledge_scan tests.test_cli tests.test_policy_shop tests.test_policy_supply
  tests.test_policy_town tests.test_policy_quest tests.test_home_entry_capture
  tests.test_latch_onset_capture tests.test_absorbing_states`; failure lists as verbatim test
  identities; re-run any "standing" failure on the parent commit before calling it standing;
  per-pin revert results.
- If a measurement contradicts this spec — the `pre1735` restore does not give `~9` as its first
  decision with A1, batch 41's response is not accepted with A2, A2-exit/A2-reentry/A2-supersede do
  not reject, the second outside decision of A2-supersede posts `~9` with A2, or an existing test
  other than the four named above (two `test_policy_town`, two `test_home_knowledge_scan`) moves —
  say so in the events log and stop. The two UNVERIFIED direct-consume tests are the first thing to
  run.

## Questions for the user (not settled by an approved decision; the supervisor puts them to the user before the codex review)

- **Q1 — Is the `~9` list a sufficient "Home attempt" under Home-first when knowledge is stale, or
  must the bot physically enter Home before a purchase?** (a) `~9` suffices — the current code's
  interpretation since `3f335e3`; this spec (A1+A2) restores it; the bot walks to Home only when the
  list shows a withdrawable stack (the candidate branch, as at 08:12 rows 23-28). (b) Physical visit
  required — then the yield branch (`policy_shop.py:1158-1167`) must be replaced by a real Home route
  through the arbiter transfer (`acquire_store_visit`, `town_arbiter.py:110-142`) and the plan must
  carry a Home stop; more walking per stale visit; a further hunk and pins. Recommendation: (a).
- **Q2 — After A1, a lost response within one visit still ends in the arbiter stop** (the rung
  allows one re-request per visit; two losses → the loop → `town:blocked:owner-retired`, visible).
  Accept that as the intended visible terminal, or should a refused scan retire the purchase claim
  (departure without buying)? Recommendation: keep the visible stop (the user rule).
- **Q3 — The two 2026-09-10 stops** (posted `shop:one-shot-buy` never landing) share the label but
  not the mechanism. Open a separate task, or leave until it recurs?

## USER ANSWERS to Q1 / Q2 / Q3 (2026-09-12, via AskUserQuestion) — BINDING

The supervisor put all three questions to the user. The answers below settle them; they are not to be
reopened by the reviewer or the implementer.

- **Q1 → 「一覧の取り寄せで十分」 (option (a)).** Requesting the Home list with `~9` IS a sufficient
  Home-first attempt when Home knowledge is stale. The bot walks to Home only when the list shows a
  withdrawable stack. The yield branch at `policy_shop.py:1158-1167` keeps its current shape; no Home
  route is added. Hunks A1 and A2 stand as designed.
- **Q2 → 「可視停止のまま」.** If two scan responses are lost inside one town visit, the arbiter's
  `town:blocked:owner-retired` remains the intended visible terminal. Do NOT retire the purchase claim
  and do NOT depart without buying. This matches the standing user rule
  「満たせない要求は可視停止で報告すること」. Acceptance must state this explicitly so the reviewer does not
  read the remaining stop as an unfixed defect.
- **Q3 → 「別タスクとして起票する」.** The two 2026-09-10 stops (a posted `shop:one-shot-buy` that never
  lands) are a DIFFERENT mechanism sharing the same label. They stay out of scope here; the supervisor
  filed them as a separate task. Keep them in "Out of scope" with that note.

No hunk, pin or acceptance line changes as a result of these answers, except that Acceptance gains the
Q2 sentence above.

## What the designer could not verify

**UNVERIFIED in round 3 (each with the exact check):**
- The two direct-consume tests (`test_home_light_alternation::test_pin_s_and_c_incident_trajectory`,
  `test_policy_home::test_public_calibration_restore_converges_twelve_items`) staying green once
  `consume_home_knowledge` settles the token. Check: `PROBE_CONSUME_SETTLES=1 PROBE_MODE=B python
  <scratchpad>/probe_r3b_tests2.py` (in-process shadow, sandboxed), or the two tests under the real
  hunks. Expected: both ok.
- (Resolved after writing: the HEAD baseline of the 267-test run finished — `failures 0, errors 4,
  skipped 3`, the same 4 environmental errors as under the shadow. Measured, not unverified.)
- A2-seed under revision 3 (post-batch-40 state `inflight True, requested True`, batch-41 row
  `accepted True, inflight_at_arrival True, settled True`). Check: `PROBE_MODE=B python
  <scratchpad>/probe_r3b_seed.py` (re-drives CK36 → batch 43 in the sandbox
  `sandbox_retired_CK36+B3b`; prints the trace of seq 36-40 and the ledger rows).
- The frequency of genuinely lost `~9` responses in live play (a lost response now costs the
  visit's Home-first attempt and ends in the visible stop). No artifact shows a loss: the incident's
  6 posts all produced a row. If losses turn out common, the remedy is a state-based proof of loss,
  not a re-request budget.
- The retry-rule deletion's effect on modules the designer did not run in-process
  (`tests.test_policy_shop` whole, `tests.test_policy_supply`, `tests.test_absorbing_states`,
  `tests.test_golden_trajectory`); the named suites in "Gates" cover them.

- The game-side key-queue ordering behind the late responses (INFERRED from the posted-character
  and recorder orders; 4/4 consistent, no game log of the queue; codex concurs).
- Any behaviour past the first hunk-caused divergence in a replay (rows after 1735 with A1; the
  decision after batch 41 with A2) — the recorded boards are live's. No pin asserts there.
- A response arriving after a real town exit does not exist in the recording (all four late
  responses were emitted in town); the exit rejection is proven on the public-path fixture with a
  synthetic dungeon board line, and the recorded exit (line 7694) only feeds CLI-town-helper. An
  optional seed variant (recorded line 7694 followed by the recorded knowledge line 7689 in one
  batch) would be re-sequenced recorded input and is not required.
- Whether the 08:17 `~9` posted on arrival at (31,150) would race a queued key in live as the
  08:13/08:14 ones did (arrival was by `<`, not by a travel macro; with A2 the race is harmless).
- The fixture pickles' portability across Python versions (existing `*-checkpoints.jsonl.gz`
  fixtures use the same mechanism).
- The full named modules under the real implementation (only 45 selected tests were run in-process
  under the shadow; the two `test_policy_town` failures are the only movers found, other modules
  that hand-set scan bookkeeping — `tests/test_policy_quest.py:3841,3889`, `tests/test_policy_shop.py:
  2398,2613` — were run and are green).
- No suite, gate or `src/`/`tests/` edit was run or made; the only writes were the sandbox
  directories and probe scripts under the scratchpad and this file (rounds 2 and 3).
