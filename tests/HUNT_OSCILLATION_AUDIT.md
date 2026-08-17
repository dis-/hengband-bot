# Hunt oscillation loop audit — corrected record

## Attribution

There is no introducing commit in `393a418..be96c3a`. Independent replay found
`_hunt_step` byte-identical through that range, and the pre-executor `b2607a7`
tree sustains the captured midpoint loop too (37 of 40 decisions remain
`hunt`, with no abandonment). The earlier attribution to `2b46250` was false.
This is latent, long-standing nearest-target behavior exposed by the captured
race-35 packs split north and south around the player.

The prompt-history behavior dates to `94ab6c2`, before the equipment executor.
In the 04:46 incident the posting-contract mismatch recovered on the next
decision and preceded the hunt loop by 55 decisions. The 07:18 stop window has
zero posting-contract incidents. It was therefore non-causal, although the
completed-history correction in `371abf3` remains independently valid.

## Cause and fix

Measured: live race-35 monsters occur on both sides of the player in
`evidence/evidence-huntloop2-20260817-0718.jsonl:1192-1200`; the chase records no
damage or experience progress; `b2607a7` and the later stack all sustain it.
Inferred: nearest-target switching around the midpoint prevents durable closure
and leaves the hunt claim absorbing. The real fix is the progress bound, not an
equipment-serialization change.

Progress is now tracked per monster identity `(index, race, first-seen
position)`, once per policy decision. A new target gets its own distance
baseline, and an index observed absent before reuse receives a fresh identity.
After `HUNT_RANGE` decisions without damage, experience gain, or closer best
distance, only that opportunistic target is cooled for the floor visit. Quest
targets are exempt. Abandonment is emitted in the additive `hunt_report` field,
so an `equipment_mutation_report` from the same decision is preserved.

## ROUND 2 acceptance pins

- The captured midpoint scenario uses `choose_key`: eight hunt decisions are
  followed by a non-hunt claim before the cell guard.
- Quest-target exemption, per-target closure, index reuse, and once-per-decision
  accounting are pinned.
- A decision row can contain both equipment and hunt reports.
- The mutation battery's public set contains the `choose_key` hunt pin and its
  stdout/stderr are explicitly UTF-8.

No full-suite discovery is claimed. The bot/game and evidence were untouched;
no push was performed.
