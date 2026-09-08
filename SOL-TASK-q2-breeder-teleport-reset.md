# SOL-TASK: Q2 abandons an engaged gremlin cluster at full health

User report (2026-09-09): 「現在突入しているクエスト下水道にてグレムリンの撃破より逃亡を優先した件を修正。
増殖を許したせいでクリアは絶望的。」

Supervisor investigation of the live quest floor (`quest_id=2`, dungeon level 15, turns
1678607–1680101, 193 decisions; the bot is stopped mid-quest with the game still running).

## What the bot actually did — the fair tally first

| reason | n |
|---|---:|
| `quest-strategy:q2-fire` | 49 |
| `quest-strategy:q2-breeder-recommit` | 48 |
| `quest-strategy:q2-phase-153` | 34 (movement keys `7/8/9/6` — routing TOWARD race 153, not fleeing) |
| `quest-strategy:melee` | 31 |
| `quest-strategy:q2-close-residual-multiplier-no-ammo` | 7 |
| `quest-strategy:q2-hunt-priority-270` | 6 |
| `quest-strategy:q2-teleport-reset` | **3** |
| `emergency:teleport` | **2** |

80 attack decisions against 5 escapes. The bot was mostly fighting. But the five escapes are where
the quest was lost, and three of them are a defect.

## The defect: `q2-teleport-reset` fires at full health

```
t=1679228  q2-teleport-reset  hp=380/381 (99.7%)  hostiles=6   key='re'
t=1679235  q2-teleport-reset  hp=378/381 (99.2%)  hostiles=6   key='re'
t=1679892  q2-teleport-reset  hp=300/387 (77.5%)  hostiles=4   key='rd'
```

Hostile counts across those resets — the breeding is visible in the data:

```
t=1679228  before [7,6,6]  at 6  after [6,0,2,3,4,4,4]
t=1679235  before [6,6,6]  at 6  after [0,2,3,4,4,4,3]
```

Teleporting away drops the count to 0 (out of sight), and it climbs straight back. Each reset hands
the breeders unopposed turns.

The trigger, `policy_quest.py:1614-1634` in `_q2_encounter_key`:

```python
melee_commit = (
    adjacent
    and all(monster.race_id == 202 for monster in adjacent)
    and self._quest_profile_ammo(snapshot, profile) is None
)
if not melee_commit and len(adjacent) >= SWARM_COUNT and not (
    snapshot.player.blind or snapshot.player.confused
):
    teleport = self._find_teleport_scroll(snapshot)
    if teleport is not None:
        self.last_reason = "quest-strategy:q2-teleport-reset"
        return self._read_key(snapshot, teleport)
```

Two things are wrong with it, and the code's own comment states the intent it is failing:

> `# Leaving an engaged breeder cluster fails Q2.`

**D1 — the breeder guard is hardcoded to one race.** `melee_commit` only holds when EVERY adjacent
monster is `race_id == 202`. The gremlins in this quest are **race 153**, so the guard never
engaged. `MonsterState` already carries `can_multiply` (`model.py:722`), and the threat telemetry
shows race 153 with `can_multiply: True` — the general predicate exists and is populated. The
hardcoded `202` is a rendering of "breeder" that misses every other breeder.

**D2 — the reset has no danger condition at all.** `len(adjacent) >= SWARM_COUNT` (SWARM_COUNT = 3,
`policy_constants.py:328`) is a pure COUNT trigger. It fired at 99.7% HP. This is the
`bot-town-count-retirement` pattern — a count standing in for a state.

## What is NOT a defect — do not "fix" it

The two `emergency:teleport` calls were justified and must not be weakened:

```
t=1679620  hp=288/387  threat_prediction total=375 over 3 turns  trigger emergency-summoner
t=1679783  hp=308/387  threat_prediction total=308 over 3 turns  trigger emergency-lethal-swarm
```

At t=1679783 the predicted 3-turn damage (308) equalled current HP (308). The prediction is also
NOT naive: the four `never_moves` breeders at distance 11-12 contribute exactly **0**, and 220 of
the 308 comes from a single race-1044 monster at distance 2. That model is working. Leave it alone.

Also not a defect: `q2-phase-153` is routing toward the gremlins (plain movement keys), not fleeing
from them. It is not evidence of flight.

## The work

**D1 (repair):** generalise `melee_commit` from `race_id == 202` to the breeder predicate the
snapshot already provides (`can_multiply`). Leaving an engaged breeder cluster fails Q2 — that is
the code's own stated rule, and it should hold for every breeder, not one race. Keep the existing
ammo condition unless your investigation shows it is wrong; say what you conclude.

**D2 (investigate first, then propose or repair):** establish WHY the swarm reset is count-only.
Find what it was written for — a real incident, a review, a task doc — and say so with the evidence.
Then:
- if it is safe to gate on the EXISTING threat model (the same `threat_prediction` that drives
  `emergency:teleport`), do it: a swarm that cannot meaningfully hurt the player is not a reason to
  abandon a quest floor;
- if the count trigger turns out to be load-bearing for a failure mode the threat model does not
  cover, PROPOSE the change and STOP — do not weaken a survival path on a hunch
  (spec-change-propose-not-implement).

**Hard requirement — no new death path.** This repair makes the bot STAY in fights it used to leave.
The pin set must include a case where the bot still leaves: a genuinely lethal adjacent swarm must
still escape. A repair that removes the escape entirely is a character-death defect, and this
character is CL20 with 387 HP on a quest floor.

## Context worth carrying

`q2-close-residual-multiplier-no-ammo` fired 7 times: the bot ran its launcher ammunition dry and
had to close to melee on the residual breeders. Whether the ammunition budget for a breeder quest is
adequate is a separate question — record it, do not fix it here.
