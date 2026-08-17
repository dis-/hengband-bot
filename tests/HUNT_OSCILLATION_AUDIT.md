# Hunt oscillation loop audit

## Attribution first

The first bad revision in the replayed `393a418..be96c3a` stack is `2b46250`
(`Serialize wield mutations and restore prompt recovery`). The pre-executor
`b2607a7` source does not sustain the captured hunt midpoint loop; commits from
`2b46250` onward do. The later `cc222aa` executor migration inherited the
regression rather than introducing it.

The captured stimulus is not stale memory. Race 35 jackals remain live north
and south of the player in
`evidence/evidence-huntloop2-20260817-0718.jsonl:1192-1200`. Nearest-target
selection alternates between the groups around the midpoint without damage,
experience gain, or durable distance closure, and only the cell guard ends the
unbounded claim.

## Combat-time equipment request class second

| producer | adjacent combat possible | executor contract | captured failure shape |
| --- | --- | --- | --- |
| mining restore-weapon | yes | full wield tail is composed from observed hands; a posted mutation serializes later mutations | no open wield prompt was observed; the sender falsely classified completed history |
| no-teleport rearm | possible with town hostiles | the same full-tail composer/serializer owns wield and takeoff | no producer-specific failure measured |
| quest launcher/opening equipment | yes | the same full-tail composer/serializer owns wield and takeoff | no producer-specific failure measured |
| calibration redress under attack | possible | the same full-tail composer/serializer owns wield and takeoff | no producer-specific failure measured |

The class seam is therefore the shared executor plus the universal posting
contract, not a hunt-site equipment exception. Every wield remains one complete
key such as `win`, `wfa`, or `wky`; no requester waits for a future prompt board.

## GAME-IO-CONTRACT entry 11 finding

The earlier out.log phrase “answers observed prompts” was wrong and that code
was removed. Wield prompts are structurally unobservable while open: snapshots
exist only at command-loop entry, the which-hand selector never reaches the
message board, and the dual-wield question reaches `messages` only after its
composed answer has completed the command, as older history rather than the
newest message.

At capture lines 1026-1030, `melee:restore-weapon` posts complete key `win`.
The next board records the dual-wield question followed by equipment/combat
messages. `_open_game_prompt` incorrectly searched all history, attributed that
completed question to an open owner, and refused melee key `2`. The fix accepts
only a prompt-shaped newest serialized message. It does not answer either wield
prompt post-hoc and does not synthesize an orphan-prompt Escape.

## Fix and defense in depth

The sender no longer treats completed prompt-shaped history as an open input
owner. Independently, a hunt claim records monster HP, player experience, and
best nearest distance. After `HUNT_RANGE` decisions with no damage, experience,
or additional closure, all targets involved in the claim are cooled for the
floor visit and `hunt:abandoned-no-damage-no-closure` is reported. Another
claim can then take over before the cell guard.

## Measured and inferred

Measured: live race-35 targets occur on both sides of the player; the capture
has no damage/experience progress during the alternating hunt; `win` completes
before the dual-wield text appears in history; the which-hand selector is never
serialized. Inferred and replay-pinned: nearest-target switching sustains the
midpoint loop, and scanning older message history caused the false
prompt-owner mismatch. No stale-monster or impassable-vein premise is needed.

## Acceptance

- `test_policy`: 2007 tests, OK.
- absorbing-state catalogue: every scenario PASS.
- `test_navigation`: 90 tests, OK.
- `test_equipment_mutation`: 9 tests, OK.
- posting-contract batch: 9 tests, OK.
- fixed-side revert proof: 2 tests, OK.
- prompt-history mutant: 21 tests, 1 intended public failure.
- hunt-bound mutant: 21 tests, 1 intended public failure.
- mutation battery verbatim: 18/18 PASS; every mutant ran 21 tests;
  `repo_tree_untouched=true`.
- fakery lint by changed test module: `test_cli.py` has 0 violations and 2
  declared findings; `test_policy.py` has 3 pre-existing violations and 93
  declared findings. The new tests add no undeclared bypass.
- `git diff --check`: no output.

The bot and live game were not started, stopped, inspected, or modified, and
no push was performed.
