# SOL-TASK: three town terminals in 30 minutes, one shared shape

On 2026-09-10 the bot ran for ~30 minutes after a 10-hour stop and hit **three different visible
terminals**, all in the town errand / equipment-transaction layer. Two of the three required a
PROCESS RESTART to clear, which is the signature of in-memory owner state that no bot-reachable
transition can release — the absorbing-state defect class.

Do not fix these as three unrelated bugs until you have decided whether they share a root. They
occur in one continuous town episode with one unchanged objective.

## Evidence

Captured slice: `jsonlog/incident-town-owner-cluster-20260910.jsonl`
(265 decisions, turns 1836000..1840105, sha256
`986d25ea6b127e497f83287cdca4cd93cc83151d9c4b3635e3fe2ea8dc9fdcb6`).
Full log: `jsonlog/bot-decisions.jsonl`.

### Terminal 1 — `town:blocked:owner-retired` (turn 1836610)

The decision sequence loops with the **turn frozen**:

```
shop:approach '1'
shop:approach '9'
town-progress-invariant:continue-observed-shop ESC
... repeats ...
town-progress-invariant:defect:store:entry-await-observation=>store:entry-await-observation '1'
town:blocked:owner-retired '5'
```

Arbiter at the terminal: `transfer_pair: [0, 4]`, `transfer_count: 2`,
`transfer_exhausted: true`, `progress: false`. **Two store owners alternate** —

- store 0: `winning_rung: "shop:home-first-before-purchase"`,
  `wanted_purchase: crossbow bolts x55 @3`, `rejection_reason: "preempted"`
- store 4: `rejection_reason: "no-store-page-observed"`

Decisive artifact — the game refused the posted keys:

```
messages: ["このコマンドは店の中では使えません。 <x6>"]
```

**The character is INSIDE a store while `shop:approach` posts direction keys `'1'`/`'9'`.**
The store rejects them six times, the turn cannot advance, and the progress invariant correctly
declares a defect. See the recorded landmine `bot-invalid-store-command-saga`.

### Terminal 2 — `stuck:wander` (turns ~1839451-1840049)

~31 of the last 60 decisions were `stuck:wander` with **gold pinned at 11635** and no floor change.
`stuck:wander` is the no-owner fallback and has no detector of its own
(recorded: `bot-town-wander-calibration-deposit`).

### Terminal 3 — `equipment-transaction:home-route-repeat-terminal` (turn 1840105)

```
arbiter: owner=equipment-txn  tenure=4  progress=false
equipment_transaction: {context: "home", entry_blocker: null}
shop_selector.town_progress_invariant.marker: "TOWN_OSCILLATION_DEFECT"
```

with a `repeated_fingerprint` over (position, gold, food, inventory tuple) — the bot re-routes to
Home, arrives at an identical state, and repeats.

## What the restarts proved

- After terminal 1 the bot was restarted with **no code change** and immediately advanced
  1836610 -> 1839451, running `shop:one-shot-in-flight`, `equipment-transaction:takeoff`,
  `identify:full`.
- **Therefore the trap is in-memory owner/visit state, not game state.** A restart clears it; no
  bot-reachable transition does. That is the defect, independent of whichever terminal reports it.

## The standing requirement this violates

`operator-never-the-detector` and the town liveness invariant: an unsatisfiable claim must
**retire itself**, and town movement is not progress. Here the claim is retired only after the
transfer budget is exhausted, and only for that one owner — the next owner re-enters the same
shape.

## What to investigate first (not a prescription)

1. **Why does `shop:approach` post direction keys while inside a store?** `store_visit` at the
   terminal reads `phase: "approaching"`, `store_type: 4`, while the game says the character is in
   a store. Either the visit's phase or the in-store detection is wrong. Settle it from
   `jsonlog/bot-posted-characters.jsonl` (the ground truth for what the game received) and the
   snapshot's store field, not from reading the router.
2. **Why does `shop:home-first-before-purchase` preempt and then not complete?** Home-first is a
   RULE (`bot-home-first-procurement`: attempt Home withdrawal BEFORE any store purchase). The
   preemption is correct; the failure is that the Home leg neither succeeds nor releases, so the
   purchase is retried forever. Terminal 3 is that same Home leg oscillating.
3. **Does the 0<->4 alternation have a single owner?** Recorded class:
   `bot-alternating-owner-defect-class` — two owners alternating without bound. The discriminator
   is the number of distinct reasons plus invariance of gold / mining / experience. Here gold is
   invariant at 11635 across terminal 2.

## Hard requirements

- **Pins must replay the CAPTURED incident**, not a constructed seed. `PIN-FIDELITY.md`
  (`../.claude/skills/bot-ops/PIN-FIDELITY.md`, repo PARENT) governs: state must be created by the
  REAL producer on the SAME instance through consumed public paths.
- Each production hunk must have a pin whose LONE REVERT flips it. Run each revert and name the
  test that actually failed, with its assertion.
- No new guard constant, latch, or budget. A restart-clears-it defect must not be fixed by adding
  a timer that gives up sooner — find why the state cannot be released and release it at its source.
- **Append a `type:"plan"` event BEFORE implementing** (pin list, seed provenance per pin, and the
  production hunk whose lone revert each pin flips). Implementation starts after acknowledgement
  or 30 minutes with no objection.

## Runtime state

- Bot is **STOPPED** and `jsonlog/maintenance.hold` is **present** — both must stay that way.
- Game `Hengband.exe` PID 17368 is RUNNING. Read-only observation only; do not stop it, do not
  save, do not touch the save files.
- The bot is currently launched WITHOUT `--capture-home-entry` (see
  `SOL-TASK-capture-log-budget.md`); do not re-enable it.

## Operational limits — hard

1. Total memory across all processes you start: **under 16 GB**.
2. **Suites run SEQUENTIALLY.** Never two full suites at once.
3. `jsonlog` must stay **under 5 GB total** (currently ~2.6 GB).
4. Note: the serial standing suite currently exits 1 on a PRE-EXISTING harness defect
   (`SOL-TASK-receipt-stderr-fileno.md`) — `io.UnsupportedOperation: fileno` in
   `tests.test_emit_ownership`. That single error is expected and is NOT yours; any OTHER failure is.

---

## VERIFICATION AMENDMENT (supervisor, 2026-09-10 02:20 — after the plan event)

The `type:"plan"` event of 2026-09-10T02:01:56 was ACKNOWLEDGED with one amendment. If you are
reading this while preparing your fix event, apply it before you ship.

The plan listed **one** `production_hunks` entry spanning two files, and **all three** pins named
that same single "entry-observation lifecycle hunk" as their lone revert. Reverting the whole
change for every pin shows only that the change as a whole is load-bearing — not which pin
depends on which part.

Required before shipping:

1. Enumerate the production change as **separately revertible hunks**. At minimum the
   store-entry-owner authority change and the staged-operation release change are distinct
   concerns in distinct files.
2. For **each** hunk: revert THAT HUNK ALONE with the others still applied, run the pins, and
   report the test that ACTUALLY failed together with its assertion. Do not attribute a failure
   you did not observe.
3. If two hunks genuinely cannot be separated, say so and argue WHY they are one atomic change.
   That is an acceptable answer, but it must be argued, not the default.
4. If a hunk exists that **no** pin flips, it is unpinned: add a pin for it or drop it. Do not
   ship an unpinned production change.

Note also: the plan named `src/hengbot/policy.py` and `src/hengbot/policy_shop.py`, but the
implementation is touching `src/hengbot/policy.py` and `src/hengbot/policy_town.py`. That may be
correct — but state in the fix event why the landing site moved, so the reviewer is not left to
infer it.
