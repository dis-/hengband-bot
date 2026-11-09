# Anaguma (穴熊): a dug Stone to Mud pocket for ambushing packs. Design (draft, not implemented)

Owner request (2026-11-10, verbatim):

> 群れに対抗するための戦術を追加する。岩石溶解を用いて7方壁の窪みを作り待ち伏せする方法である。後続から遠距離攻撃を受けないようにしておくとなお良い。穴熊と呼称する。

In English: add an anti-pack tactic named 穴熊 (Anaguma).
- Use Stone to Mud to dig a pocket where 7 of the player's 8 neighbours are wall.
- Wait in it for the pack (an ambush), so only one enemy can melee at a time.
- Even better if the monsters queued behind the front one cannot use ranged attacks on the player.

This document does not narrow the request or add caps. Where a choice is not the owner's yet, it is listed in section 9 as an open question with options and a recommendation.

Citations:
- Game paths are relative to `C:/hengband/src` (or `C:/hengband/lib`).
- Bot paths are relative to this repository (`bot-client`).

Notation:
- `P` is the pocket cell, where the player stands.
- `M` is the mouth: the single open neighbour of `P`.
- "Follower" means any pack member that is not on `M`.

---

## 1. Game mechanics (verified in C++)

### 1.1 Stone to Mud

**Effect.** `wall_to_mud` (`spell-kind/spells-beam.cpp:14-18`) is `project_hook` with `AttributeType::KILL_WALL` and the flags `PROJECT_BEAM | PROJECT_GRID | PROJECT_ITEM | PROJECT_KILL`. The beam follows the projection path.

**Which cell it melts.** The path ends at the first grid without `PROJECTION` (`target/projection-path-calculator.cpp:78-110`, `project_stop`). Monsters do not stop it, because `PROJECT_STOP` is not set. So **one use melts exactly the first wall on the line**. Open floor in front of that wall does not stop the beam. This means two zaps in the same direction dig two cells deep without moving.

**Terrain effect.** `effect/effect-feature.cpp:232-245`:
- Only terrain with the `STONE` flag is affected. It goes through `cave_alter_feat(..., STONE)` (`grid/grid.cpp:857`).
- The `STONE` action maps to `TerrainAction::DESTROY` (`system/terrain/terrain-definition.cpp:20`).
- `DungeonDefinition::convert_terrain_id` (`system/dungeon/dungeon-definition.cpp:40-52`) returns `PERMANENT` terrain unchanged. Any other terrain becomes its `destroyed` result, which is `*FLOOR*` (the dungeon's floor kind).
- The flow is recalculated: `DeferredUpdateRequests ... FLOW`, `effect-feature.cpp:243`.

**Terrain flags** (`lib/edit/TerrainDefinitions.jsonc`):

| Terrain | Has STONE | Flags line | Result |
|---|---|---|---|
| Granite, including the `_INNER`/`_OUTER`/`_SOLID` variants used by rooms and vaults | yes | `:1768` and the following entries | melts |
| Magma vein | yes | `:1602` | melts |
| Quartz vein | yes | `:1625` | melts |
| Rubble | yes | `:1580` | melts |
| Closed, locked and jammed doors | yes | `:1017`, `:1320`… | melt |
| `PERMANENT`, `PERMANENT_INNER`/`_OUTER`/`_SOLID` (`:1844-1930`) | no | `:1856` | never melts; ends the beam |
| Trees | no | — | not a wall anyway (they have `MOVE`) |

The bot approximates STONE as `tunnel and not permanent` (`src/hengbot/sealed_pocket.py:15-22`, `walkout_dig.py:50`). That is correct for every wall kind above.

**Damage to monsters.** It only hurts `HURT_ROCK` monsters (`effect/effect-monster-switcher.cpp:103-121`). For everything else the damage is 0, so it is not a weapon.

**Sources of the effect:**

| Source | Location | Notes |
|---|---|---|
| Wand of Stone to Mud | `cmd-item/cmd-zapwand.cpp:138-144`; 20+1d30, or 40+1d60 when powerful | bot: `SV_WAND_STONE_TO_MUD = 6` (`src/hengbot/model.py:406`) |
| Rod of Stone to Mud | `cmd-item/cmd-zaprod.cpp:268-274` | the bot never aims a rod today (section 6) |
| Arcane spell | `realm/realm-arcane.cpp:305` | |
| Nature spell | `realm/realm-nature.cpp:195` | |
| Elementalist | `mind/mind-elementalist.cpp:1489` | |
| Half-Giant racial | `racial/racial-switcher.cpp:358-365` | |
| Item activation | `object-activation/activation-others.cpp:128` | |
| Absorbed Magic-Eater wand | `cmd-item/cmd-magiceat.cpp` | |
| Sniper `SP_KILL_WALL` | `combat/shoot.cpp:624-640` | |
| Samurai `HISSATSU_HAGAN` | `combat/slaying.cpp:251` | |

**Turn cost.**
- One use takes a full player turn: 100 energy (`object-use/zapwand-execution.cpp:58`, `object-use/zaprod-execution.cpp:61`).
- A device failure also takes the turn and keeps the charge (`zapwand-execution.cpp:68-83`). The expected cost of one dig is therefore `1 / p_success` turns.
- Range is `get_max_range()` = 18 (`system/angband-system.cpp:45-48`). This does not matter here, because every dig is at distance 1.
- The bot can only aim in the 8 directions (`me_powers.beam_direction`, `src/hengbot/me_powers.py:331`). Every dig below is adjacent to an open cell in one of the 8 directions, so that is enough.

### 1.2 Line of sight vs projectable, and monsters in the way

**`los()`** (`floor/line-of-sight.cpp:45-...`):
- It is terrain only. Monsters never block it.
- Adjacent cells always see each other (`:51-53`).
- A knight-move (1,2) is visible if the orthogonal cell next to the *source* is open (`:105-117`).
- It is not symmetric.

**`projectable()`** (`target/projection-path-calculator.cpp:262-272`):
- The projection path is built with flags 0, so monsters do not block it.
- It is true when the path reaches the destination.
- This is the test monsters use to decide whether they can cast at the player.

**Monsters in the line:**
- **Bolts are blocked by monsters in the line.** A non-STUPID monster drops all bolt spells unless `clean_shot` holds (`mspell/mspell-attack.cpp:106-109`). `clean_shot` (`mspell/mspell-checker.cpp:125-160`) fails if any non-pet monster stands on the path.
- So with a 1-wide queue, followers on the same line as `P`–`M` cannot bolt past the front monster.
- **Breaths and balls are not blocked by monsters.** `breath_direct` / `project` only stop at terrain.

**The corner trick: indirect targeting.** This is the most important finding for the "なお良い" part of the request.
- When a monster cannot `projectable()` the player, `decide_lite_projection` (`mspell/mspell-lite.cpp:209-226`) calls `adjacent_grid_check` (`mspell-lite.cpp:39-87`).
- That function looks for a cell next to the player that has the `PROJECTION` terrain flag and is `projectable` from the monster, and retargets the spell there.
- From an off-player target, `check_thrown_mspell` (`mspell/mspell-attack.cpp:211-262`) forbids every direct-only ability: bolts, `CAUSE_*`, `MIND_BLAST`, `BRAIN_SMASH`, `DRAIN_MANA`, `SCARE`, `BLIND`, `CONF`, `SLOW`, **`HOLD` (paralysis)**, `HAND_DOOM`, **`TELE_TO`**, `TELE_AWAY`, `TELE_LEVEL`, `PSY_SPEAR`, `DARKNESS`, `FORGET`, `DISPEL`, `SHOOT`, `MISSILE`.
- Everything else is still allowed at the redirected cell: **breaths, balls, storms and summons**.

In a pocket, the only neighbour of `P` with `PROJECTION` is `M`. So a follower that cannot see `P` but can project to `M` can still breathe or ball at `M`.

**Blast reach and damage.**
- `ball_shape` (`spell/range-calc.cpp:267-291`) covers every grid within `rad` of the centre that is `projectable` from it (`is_prevent_blast`, `range-calc.cpp:16-31`). `P` is adjacent to `M`, so a ball centred on `M` always reaches `P` when `rad >= 1`.
- `breath_shape` (`range-calc.cpp:215-265`) extends `rad` past the target (`mdis = distance + rad`), so it reaches `P` as well.
- The player takes `(dam + r) / (r + 1)` at distance `r` (`effect/effect-player.cpp:209`). At `r = 1` that is **about half damage**.
- The player's own balls never hurt the player (`effect-player.cpp:140-142`). So the player can safely ball `M` from `P`.

**Conclusion.** No pocket shape stops a follower from breathing or balling at `M`. A concealed pocket does three things:
1. It removes every direct-only attack from followers. That includes paralysis (`HOLD`) and teleport-to (`TELE_TO`).
2. It halves follower breaths and balls.
3. It limits which follower cells can reach `M` at all (section 2.3).

The monster standing **on `M`** is adjacent, so it can use every attack directly.

### 1.3 Summons

- A summon spell is dropped unless `summon_possible` (`mspell/mspell-checker.cpp:36-61`) finds an empty cell within distance 2 of the target that is projectable both ways from it. The check is at `mspell-attack.cpp:111-113`.
- Summoned monsters are placed by `mon_scatter` within 2 of the target, on cells projectable from it (`monster-floor/monster-generator.cpp:42-66`, called from `monster-floor/monster-summon.cpp:47`).
- In a concealed pocket, the front monster targets `P` directly. But no empty cell within 2 of `P` is projectable from `P` (`M` is occupied, see 2.3), so **the front monster cannot summon**.
- Followers retarget to `M` and can summon into the queue cells near `M`. They can summon onto `M` itself only while `M` is empty.

### 1.4 Monsters that ignore walls

- **`KILL_WALL`** (`monster-floor/monster-move.cpp:76-81`): the monster destroys any `CAN_DISINTEGRATE`, non-`PERMANENT` wall it walks into. It can reach `P` from any of the 7 wall sides.
- **`PASS_WALL`** (`monster-move.cpp:96`): the monster walks through `CAN_PASS` terrain. Granite, veins and rubble have it; `PERMANENT` walls do not (`TerrainDefinitions.jsonc:1856`).
- A pocket backed by permanent walls therefore stays closed even to wall-passers on those sides.
- Ordinary monsters do not dig.
- The bot already counts "wall slots" usable only by such monsters (`src/hengbot/policy_combat.py:3732`, `_melee_adjacency_slots`; used in `threat_prediction`, `:3619-3650`).

### 1.5 Pack animals will not walk into the pocket (crucial)

`MonsterMoveGridDecidersFactory` (`monster-floor/monster-sweep-grid.cpp:479-487`) gives every hostile monster with `FRIENDS` (`HAS_FRIENDS`) **and** `ANIMAL`, and without `PASS_WALL`/`KILL_WALL`, the `HidingMoveGridDecider` first. The precondition is that the monster sees the player or is within 10 flow steps (`MAX_PLAYER_SIGHT / 2`, `system/gamevalue.h:19`).

How it decides (`monster-sweep-grid.cpp:198-230`):
- `room` = the number of the **player's** 8 neighbours the monster can enter.
- Subtract 2 if the player's grid is a room grid.
- Subtract 2 if the monster has no spells at all.
- The monster approaches only if `room >= 8 * (chp + csp) / (mhp + msp)` (integer division).
  - **`chp`, `csp`, `mhp`, `msp` are the PLAYER's** current and maximum HP and SP (`this->player_ptr->chp`…, `monster-sweep-grid.cpp:218-225`). The monster's own HP does not enter the test.
- Otherwise it moves to a hiding cell (`find_hiding`, `monster-floor/monster-safety-hiding.cpp:114-162`). That is the cell that:
  - is found in the first ring around the monster (distances 1 to 9, `DIST_OFFSETS`, `monster-floor/monster-dist-offsets.cpp`) that holds any candidate;
  - is empty and enterable (`monster_can_enter` refuses a cell holding a monster or the player, `monster/monster-info.cpp:132-143`);
  - is **not projectable from the player**;
  - is reachable from the monster by a `clean_shot` (no monster on the line);
  - lies at distance 2 or more from the player;
  - and, among those, is closest to the player.

Inside a pocket, `room` is 1 at the player's full HP and SP:
- **Breathing hounds** (`Z`: fire, air and light hounds, all `ANIMAL FRIENDS` with a breath) close in only once the **player's** `(HP+SP) / (maxHP+maxSP)` is below 25%.
- **Spell-less pack animals** (jackals, wolves: `ANIMAL FRIENDS`, no skills) have `room = -1` and **never** close in on their own.
- Both kinds sit hidden just out of the player's projection, at distance 2. Hounds can then breathe at `M` from there (1.2).

The owner's answer (1.7) uses the hiding rule against them.

The bot already met this in corridors. See the docstring of `_choke_stall_released_for` (`src/hengbot/policy_combat.py:3970-3986`).

Non-animal packs approach normally and queue up. They have `FRIENDS` without `ANIMAL`; for example cave orcs and snagas (checked in `lib/edit/MonraceDefinitions.jsonc`). They may use `SurroundingMoveGridDecider` when within 3, but in a pocket there is nothing to surround.

Two results follow:
- A *short* pocket works as described for non-animal packs.
- Against animal packs a short pocket produces a stand-off. The owner's long zigzag (1.7) solves that.

### 1.6 Reachability, teleport-to and breeders

- **Reachability.** `M` is reachable whenever the pocket was dug from a reachable cell. After the dig, flow is recalculated, so monsters path to it.
- **Teleport-to.** `TELE_TO` is direct-only (1.2). Only the monster on `M`, or a follower that can project to `P` in a non-concealed pocket, can pull the player out.
- **Breeders.** A breeder multiplies with probability 1/(8k), where `k` is the number of monsters in its 3×3 including itself. It never multiplies at `k >= 4` (`monster/monster-processor.cpp:498-538`; owner memo breeder-area-kill-decision-20261108). A 1-wide queue keeps `k` at 2-3, so breeders in the queue keep multiplying, but only into empty cells.

### 1.7 Owner's answer for animal packs: a long zigzag (verified)

Owner (2026-11-10, verbatim):

> 動物の群れにはジグザグの通路を長めに取る。すると、動物の後退する動きが後続に阻まれ順に近寄ってくる。最後の一匹は近寄ってこないのでこちらから詰める動きが別途必要になる。

In English: dig a long zigzag tunnel for animal packs. Their backing-off moves are blocked by the animals behind, so they come in one by one. The last one will not come, so a separate move to close in on it is needed.

The owner's diagram (`C:/hengband-backups/pdca/anaguma/owner-zigzag-1110.png`) shows a long tunnel dug one cell per row, alternating between two columns (every step diagonal, each turn 90°), with `@` at the inner end.

**Why this works, in C++:**

1. **Pack-mates cannot swap.**
   - A move into a cell holding another monster sets `do_move = false` (`monster-attack/monster-attack-processor.cpp:120-150`).
   - It proceeds only by KILL_BODY, which needs a higher `mexp * level`, or by MOVE_BODY, which needs the flag and a strictly higher `mexp`.
   - Same-race pack-mates have equal `mexp`, so neither applies.
   - The movement loop then tries the remaining directions of the list (`monster-floor/monster-move.cpp:378-440`). Those are the primary direction, ±45° and ±90° (`monster/monster-processor-util.cpp:83-163`). In a 1-wide tunnel every other direction is a wall.

2. **Hiding needs an empty cell on a clean line.**
   - `find_hiding` only accepts empty cells (`monster-info.cpp:139`) that the monster can `clean_shot` (`monster-safety-hiding.cpp:129`).
   - In a 1-wide zigzag, the walls at each 90° turn break every straight line along the tunnel. The tunnel cells two or more steps away are therefore not clean-shot targets.
   - The next cell back is reachable but occupied by the follower.
   - The search widens to rings 2 to 9. In a tunnel dug into rock those rings hold only walls and further tunnel cells, and those fail the clean line or are occupied. Corridor cells can be found only when the tunnel is short.
   - So `find_hiding` returns nothing.

3. **The fallback decider closes in.**
   - With no hiding cell, the next decider is `SurroundingMoveGridDecider` (`monster-sweep-grid.cpp:239-273`). It is added when the flow distance is under 3 (`:486-488`).
   - It moves the animal to a free neighbour of the player. In a pocket that can only be `M`.
   - Once the animal stands on `M`, the same decider returns the player's own cell, so the animal attacks (`:258-261`; the attack is in `monster-attack-processor.cpp:32-...`).

4. **The front animal is pinned; the last one is not.**
   - When the front animal later tries to back off, its retreat is blocked by the follower that has stepped into `D`. So it stays on `M` and fights, and the player can melee it.
   - The last animal has nobody behind it. Its retreat succeeds every time, so it sits hidden at distance 2 or more inside the tunnel, typically on `D`. This is exactly the owner's 「最後の一匹は近寄ってこない」.

**Simulation.** I ported the decision chain to Python, reusing the bot's port of the projection path:
- the hiding decider with the exact `DIST_OFFSETS` table, `Grid::calc_distance`, `clean_shot` and `monster_can_enter`;
- the surrounding decider;
- `get_moves_val`;
- the movement loop with no swapping.

Setup:
- Corridor along row 0. Tunnel cells `c_k = (-k, k mod 2)`, as in the diagram.
- The player sits at full HP on `P = c_L` and kills the monster on `M` after 1, 2, 3 or 6 player turns.
- N = 3, 6 or 10 animals start in the corridor. 5 seeds, random turn order.

| Tunnel | Animals that came to `M` and were killed | Left |
|---|---|---|
| zigzag L = 3 | N - 3 (the 3 closest stay out) | 3 |
| **zigzag L >= 4 (tested 4, 5, 6, 8, 10, 12)** | **N - 1 in every run** | **1, the last one, hidden on `D` or nearby** |
| straight L = 3 to 12 | N - 2 | 2 |

The result is the same with and without spells (`room` 1 or -1), and at 50% player HP.

**Why at least 4 cells.** `P`, `M`, `D` and the cell behind `D` (`B`) must all lie inside the 1-wide tunnel:
- That gives `D` exactly 2 open neighbours, `M` and `B`.
- So a single follower on `B` closes the front animal's retreat.
- With L = 3, `D` touches the corridor, which has 4 open neighbours for `D`, so the retreat cannot be blocked.

**Exposure of the long zigzag (L >= 4):**
- Concealed: no cell projects to `P`.
- **Only `D` can project to `M`** (computed for L = 4 to 8). So only the single animal on `D` can breathe or ball at `M`, for about half damage. That is the follower ranged attack the owner wanted to avoid, now reduced to one cell.
- A ball centred on `M` reaches `P`, `M` and `D` only (radius 1 to 3). In this shape, the player's area attacks hit exactly the next animal in line.

The simulator is in Claude's scratchpad, `anaguma_sim.py`. It is a port, not the game: section 8 asks for a live confirmation through the control server before stage 5 ships.

---

## 2. Geometry

### 2.1 Definitions

- **Pocket `P`:**
  - exactly one of its 8 neighbours is open (`M`);
  - the other 7 are known walls, either permanent or STONE;
  - `M` is reachable by walking from the current cell.
- **Concealed:**
  - no open cell other than `P` and `M`, within range 18, satisfies `projectable(X, P)`;
  - the bot also checks `los(X, P) == False`, using the existing port `quest25_geometry.los` (`src/hengbot/quest25_geometry.py:150`).
- **Follower reach:** the set of open cells `X` with `projectable(X, M)`. These are the only cells from which a breath or ball can reach the player at about half damage.

The numbers below come from an exhaustive search. It uses the bot's ports of the game's projection path (`src/hengbot/projection_path.py`, a port of `projection-path-calculator.cpp`) and `los` (`quest25_geometry.py:150`). For each shape it enumerated every way to dig k cells (k up to 4) next to:
- a straight corridor,
- a dead end,
- a room wall.

### 2.2 Results (the corridor runs along row 0; the dig goes north, negative y)

| Starting place | Shape (cells dug, in order) | Digs | `P`'s open neighbours | Cells that can project to `P` | Follower reach (cells that can project to `M`) |
|---|---|---|---|---|---|
| Straight corridor | 1-cell notch `(-1,0)` | 1 | **3** (three corridor cells): not a pocket | — | — |
| Straight corridor | I-shape `(-1,0),(-2,0)`, `P=(-2,0)` | 2 | 1 | 1: `(0,0)`, the corridor cell in line | 5 |
| Straight corridor | step `(-1,0),(-2,1)`, `P=(-2,1)` | 2 | 1 | 2: `(0,-1),(0,0)` | — |
| Straight corridor | **zigzag `(-1,0),(-2,1),(-3,0)`, `P=(-3,0)`, `M=(-2,1)`** | **3** | 1 | **0 (concealed)** | **3: `(-1,0),(0,-1),(0,0)`** |
| Dead end at `(0,0)`, heading east | natural dead end | 0 | 1 | 11 (the whole corridor line) | — |
| Dead end | diagonal notch `(-1,1)` | 1 | 1 | 1 | — |
| Dead end | `(-1,1),(-2,1)` | 2 | 1 | **0 (concealed)** | — |
| Room wall | I-shape, 2 deep | 2 | 1 | **40** (the room sees down the shaft) | — |
| Room wall | zigzag (as in the corridor) | 3 | 1 | **0 (concealed)** | — |

**Note on the owner's screenshot** (@ in a one-cell notch beside a corridor). Beside a *straight* corridor a one-cell notch has 3 open neighbours: the three corridor cells. It meets "7 walls" only when cut diagonally off a dead-end tip, or where the corridor bends. A straight corridor needs at least 2 digs.

### 2.3 The default: the owner's long zigzag (at least 4 digs, staged)

The shape follows the owner's diagram. Cells are `c_k = (-k, k mod 2)` from a corridor along row 0, and the player ends on `P = c_L`.

```
row -6   # P #        P = c6 (last dig)
row -5   # # M #      M = c5, the mouth
row -4   # D #        D = c4, the next in line
row -3   # # B #      B = c3
row -2   # c #
row -1   # # c #      c1 = first dig
row  0   . . . . .    corridor
```

How to dig it:
1. From the corridor cell under `c1`, zap `8` to melt `c1`, and step in.
2. From each `c_k`, zap the diagonal (`9` or `7`, alternating) to melt `c_{k+1}`, and step in.
   - Each cell takes 1 zap and 1 step.
   - Two cells can never be dug with one line of zaps, because consecutive cells are not on one straight line.
3. Cost: L zaps plus L steps, which is `2L` player turns plus `L * (1/p - 1)` for device failures.
   - L = 4: 8 turns. L = 6: 12 turns.

**Every stage can be used:**

| Stage | What it is | Good against |
|---|---|---|
| after `c2` | a 7-wall pocket (`P = c2`) with 2 corridor shooters (2.2) | non-animal packs |
| after `c3` | concealed, but follower reach is 3 cells | non-animal packs; animal packs stay out (1.7: 3 animals stay out) |
| **`c4` and deeper** | concealed; follower reach is only `D`; animal packs come in one at a time | all packs (1.7) |

So the dig may stop at the stage the time budget allows (3.3). Stopping before L = 4 is useful only against non-animal packs.

**Properties at L >= 4** (computed with the ports, 1.7):
- **One attacker.** Only `M` touches `P`.
- **Single-file queue.** `M`'s and `D`'s only open neighbours are the previous and next tunnel cells.
- **Concealed.** No cell projects to `P`. So no follower can bolt, paralyse, teleport-to, confuse, blind, mind-blast or brain-smash the player.
- **Follower breath and ball reach is `D` only**, at about half damage.
- **No summons by the front monster** (1.3). Followers' summons land in the tunnel behind `M`.
- **Player's offence.** Melee on `M`. A ball aimed in the direction of `M` hits `M` and `D` (radius 1 to 3). Bolts, arrows and beams reach `M` only.

**Mirror and rotation.** The shape works in all 4 orientations and both handednesses. Tunnels into a room wall behave the same: only the tunnel cells matter, because the room cannot see down a zigzag. The search runs on the real known map rather than a template.

The earlier 3-dig zigzag (`(-1,0),(-2,1),(-3,0)`) is the same shape at L = 3.

### 2.4 Requirements on the map (what the bot can see)

- Every cell of the dig, and every neighbour of `P` and of `M` that must stay wall, must be **known** in `snapshot.grids` / remembered grids (`GridState.known`, `.wall`, `.tunnel`, `.permanent`, `src/hengbot/model.py:858-909`).
- A wall cell must be `wall and (tunnel or permanent)`. Unknown cells count as open: this is the conservative rule `_may_project` already uses (`src/hengbot/policy_combat.py:4616`).
- A dig target must be `tunnel and not permanent` (`sealed_pocket.can_melt`, `src/hengbot/sealed_pocket.py:240`).
- **Re-check after every dig.** A melted cell can reveal open floor behind it, such as another corridor or a room. If a neighbour of the planned `P` turns out open, re-plan from the cells already dug, or abandon.
- Avoid vault interiors (`CAVE_ICKY`) and quest-map cells, which fall under the quest exemptions in section 3.4. Prefer granite: permanent walls on the outside are even better (1.4).
- The openness count must ignore monsters, as `_open_neighbor_count` already does (`src/hengbot/policy_navigation.py:1060`). With openness 1, the existing code already treats `P` as a choke (`policy_constants.py:442`, `SUMMONER_CHOKE_NEIGHBORS = 3`).

### 2.5 Choosing where to dig

1. Search the cells reachable within a small walking budget, using the same BFS as `_validated_choke_route` (`src/hengbot/policy.py:16393`). Keep the rule that the destination is no closer to the hostiles than the player is now.
2. For each wall face that borders a reachable open cell `S`, enumerate the zigzag of 2.3 in all orientations, at every length from 2 up to the budget. Also enumerate the dead-end variants of 2.2. Every tunnel cell and every wall around it must be known rock (2.4).
3. Score each candidate:
   - fewer digs and fewer walking turns (`walk + digs / p_success` must fit the time budget of 3.3);
   - concealed before basic;
   - smaller follower reach;
   - permanent outer walls;
   - farther from the pack.
4. A natural cell with openness 1 needs **0 digs** and is the cheapest pocket. Dead ends are found this way. It is still scored on concealment.

---

## 3. Triggers

### 3.1 Which packs

The design reuses the existing pack detection rather than inventing a new one. There is no FRIENDS/`Z` logic in the bot today (survey: `knowledge.symbol` is read only at `src/hengbot/attack_expectation.py:121`).

| Existing signal | Where | What it means |
|---|---|---|
| Visible melee swarm | `_melee_swarm_combat_key`, `src/hengbot/policy_combat.py:3792-3968` | at least 2 converging melee-only monsters; predicted damage between 10% and 50% |
| Detected pack | `_detected_threat_preparation_key`, `src/hengbot/policy.py:16464-16643` | a breeder, or at least 2 awake melee-only monsters within 3 |
| Surrounded | `SWARM_COUNT = 3`, `policy_constants.py:496` | — |
| Tier | `threat_tiers.tier_of` / `assess`, `src/hengbot/threat_tiers.py:1535`, `:1069` | T1 / T2 / T3 and instant death |

What Anaguma adds:
- **The concealed pocket makes ranged followers acceptable.** Today the swarm rung declines any pack with a ranged member (`policy_combat.py:3839`). In a concealed pocket, followers can only breathe or ball at `M` for about half damage. A pack with ranged members becomes eligible when the half-damage reach, re-run through `threat_prediction` with `M` as the only melee slot, is always used (decision 「常に使う」, section 9): high-damage individuals are left to the survival rungs above.
- **Monster flags read** from `MonraceKnowledge.flags` / `abilities` (`src/hengbot/monrace_knowledge.py:46`, `:203`): `FRIENDS`, `ANIMAL`, `PASS_WALL`, `KILL_WALL`, `TELE_TO`, `S_*`, `BR_*`/`BA_*`, `MULTIPLY`.
- **Hounds (`Z`) and other animal packs** (`ANIMAL` and `FRIENDS`, no wall-passing) need the long zigzag, L >= 4 (owner 2026-11-10, 1.7). They also need the close-in move for the last one (5.1).
  - A dig that cannot reach L = 4 in time, or with the available charges, is not started against them, because L <= 3 leaves them outside (1.7).
  - Non-animal packs can use any stage from L = 2.

### 3.2 When not to dig

| Condition | Why | Source |
|---|---|---|
| Any pack member, or a visible or detected non-pack threat, has `PASS_WALL` or `KILL_WALL`, unless every wall touching `P` is permanent | they come through the 7 walls | 1.4 |
| No Stone to Mud means, or a means whose `p_success` puts `walk + digs/p` over budget | time | 1.1, 3.3 |
| Charges after the dig would fall below the reserve | the sealed-pocket escape needs one | decision: 1 kept, none for a Magic-Eater (section 9) |
| The pack arrives before the minimum stage can finish: L = 2 for non-animal packs, L = 4 for animal packs | a half-dug notch is worse than the corridor; L <= 3 does not pull animals in | 3.3, 1.7 |
| A follower-reach threat makes the half-damage prediction at least `ENGAGEMENT_AVOID_DAMAGE_RATIO` (0.5, `policy_constants.py:549`) or reaches instant death (`threat_tiers.instant_death`, `:1036`) | the pocket still takes about half of every breath | 1.2 |
| Tier T1 (cannot win even with supplies) and the tiers say leave (`leave_due`, `threat_tiers.py:1186`) | a pocket does not change "cannot win"; the existing leave rules stay first | owner 11-07 tiers design |
| Town, wilderness, surface | permanent buildings; the existing town rules | — |
| Fixed-quest floors with an owner-approved plan (Q14, Q18, Q25, …) | "作戦が先" (the plan comes first), owner 11-07 | `quest_find_exit`, `quest25_battle` |
| Arena (闘技場) | no digging in the arena; separate rules | memory telmora-arena-facts |

### 3.3 Distance and time budget

- `T_dig = walk(S) + Σ (1 / p_success)` over the remaining digs, in player turns at the player's speed.
- `T_arrive` for each awake, approaching member is its flow distance to `M` divided by its moves per player turn. Speeds come from `threat_tiers.adjusted_speed` (`threat_tiers.py:255`); detected monsters use the same.
- **Start** when `min T_arrive > T_dig(minimum stage) + 1`:
  - for a non-animal pack the minimum stage is L = 2: 2 zaps and 2 steps;
  - for an animal pack it is L = 4: 4 zaps and 4 steps, about 8 player turns at p = 1.
- **Keep digging** (the owner's 「長めに」) while `min T_arrive > T_dig(one more cell) + 1` and the terrain and charges allow, up to 8 cells (section 9). Then stand on the innermost cell.
  - Every extra cell lengthens the hidden queue.
  - In the simulation, L >= 4 already gave the N - 1 result (1.7). The benefit of extra length beyond 4 is buffer against arrival-time error and against the pack overflowing into the corridor, not a better pull-in.
- **Detected packs** (ESP or detection) are the natural ambush case, since they give the most lead time. This is where the owner's 待ち伏せ fits best.

### 3.4 Quest, floor and level scope

Default proposal: every ordinary dungeon floor, including random-quest floors, where the map is a normal cave. Fixed quests are excluded (decision 「ランダムクエストの階も使う」, section 9).

---

## 4. Interactions with existing behaviour and owner decisions

| # | Existing rule or code | Interaction | Conflict / resolution |
|---|---|---|---|
| 1 | Owner 10-23 「隘路が無ければ後退しない」; `_detected_threat_preparation_key` returns None when no choke route exists (`src/hengbot/policy.py:16636-16643`), pinned by `tests/test_detected_pack_no_choke_recorded.py` | Anaguma *creates* a choke where none exists. It is a new action, not a retreat to a missing choke. | Insert Anaguma before that None. The pin still holds whenever Anaguma is not possible (no means, wall-passers, …). That pin is a pack of large kobolds behind a wall, so the pin will need a re-read; the decision is 「掘れるなら掘る」 (section 9). |
| 2 | `_melee_swarm_combat_key` / `_choke_engagement_key` / `ChokeEngagementPlan` (`policy_combat.py:3792`, `:4042`; `policy_types.py:543`) | Same purpose. A pocket is a choke with openness 1. | Reuse `ChokeEngagementPlan` with new phases `dig` and `hold` and a `pocket` field, so the release rules (HP < 40%, damage ≥ 50%, 300-decision budget, ranged release) carry over. Ranged packs are always taken (section 9). |
| 3 | `_choke_stall_released_for` (`policy_combat.py:3970`) | Corridor chokes stall against animal packs (1.5). A zigzag of L >= 4 pulls them in (1.7); a shorter pocket stalls the same way. | The stall release stays for corridor chokes. For an Anaguma plan of L >= 4, the stall check is replaced by the last-one rule (5.1). |
| 4 | Owner 10-20 keep-all Stone to Mud wands (`policy_home.py:2693-2703`) | Anaguma spends charges. Wands are never sold. | No conflict. Recharging uses the existing facility path (the quest-2 tower trip, `q2_tower_recharge.py`). Reserve: section 9. |
| 5 | Owner 11-05 sealed pocket: melt out after *Destruction*, with Stone to Mud before Teleport (`sealed_pocket.py`) | Needs a charge left. Also, a pocket where the player stands is "all walls but one" and must not be mistaken for a sealed pocket. | `sealed_pocket.key` must ignore a pocket the bot dug itself while `M` is open. Keep a reserve (section 9). |
| 6 | `retreat_enclosure.py` (dig, then Stone to Mud, then Teleport when a retreat is boxed in) | Inside a pocket, "flee on foot" has no step. | In the pocket, flee means Teleport, Recall or *Destruction* (owner 11-04 rules: `destruction-use-decision`, `teleport-follower-decision`). `_flee_step` must not be asked. |
| 7 | `_forbid_wait_while_damaged` (`policy_combat.py:643-712`) rewrites a bare WAIT after HP loss | A pocket hold is a WAIT while monsters queue. | Add an `anaguma:hold` reason ending in `:hold` (already allowed), plus `cli.STATIONARY_REASONS` (`cli.py:390`). |
| 8 | Summoner rules: owner 11-04 (shoot the summoner first; 2 unseen summons means leave; 3 on a floor means recall); owner 11-06 (low HP plus a summoner means teleport or recall) | The front monster cannot summon (1.3); followers can summon into the queue. | Keep 11-04 and 11-06 as they are. Counting summons per floor still triggers recall. |
| 9 | `summoner_wait.hold_key` (`summoner_wait.py:116`, 50 game turns) and the detected hold (500 game turns, `policy_constants.py:441`) | Waiting bounds | Decision: 50 game turns, then a detection if available (section 9). |
| 10 | Threat tiers 11-07 (instant death first; T1 leave; T2 supply fight; `worsens_with_time`) | The pocket changes `melee_slots` to 1 and follower reach to half. | Call `threat_tiers.tiered(..., melee_slots=1)` as the choke release already does (`policy_combat.py:4089`). Add a "redirected blast" term: each follower-reach monster's ball or breath × about 0.5. Instant death stays first. |
| 11 | Breeders: owner 11-08 and 11-09 (shoot breeders in the line with area attacks; a 100-action window) | The queue is a perfect area target at `M`. | Area attacks at `M` count kills per the 11-09 rule (total damage compared with single-target). No conflict. |
| 12 | Owner 11-07 「眠っている敵でも強い敵からは離れる」 | Do not dig near a strong sleeper: digging makes noise. Each zap is a turn, and monsters wake. | Exclude a candidate within the wake radius of a T1 sleeper. |
| 13 | Owner 11-08 one-shot sensed rule (a sensed monster's one breath ≥ max HP means a resistance potion or leaving) | Stays first. Half damage at the pocket does not override it. | No conflict. |
| 14 | Owner 11-09 shallow paralyzers: flee | A concealed pocket blocks `HOLD` from followers, but not from the monster on `M`. | The rule stays: flee. |
| 15 | Owner 11-04 maze veto ("teleport, then recall") | Mazes are mostly permanent-walled. Anaguma rarely applies there. | — |
| 16 | `dungeon_ladder.LADDER` (`src/hengbot/dungeon_ladder.py:126-141`) and `scripts/dungeon_ladder_lint.py` | A new rung | Place `_anaguma_key` in pre-combat **before** `_choke_engagement_key`, and add a table row in the same commit. Also update the reason registry (`reasons.py`, `scripts/reason_registry_lint.py`), `@claims(ClaimOwner.POSITIONING)`, and the town tables if required (`town_hold.py:1845`). |
| 17 | `_should_flee` (`policy.py:9912`): 3 or more adjacent and ≥ 60% damage | In a pocket only 1 can be adjacent. | No conflict. Wall-passers are counted through wall slots. |
| 18 | Quest plans' own choke cells (`quest_find_exit.py:140-910`) | Quest plans come first. | Excluded (3.2). |

---

## 5. Fighting in the pocket

**Hold.**
- Stand on `P`. When `M` is occupied, melee it.
- When `M` is empty and a follower is in reach, use the best area attack centred on `M`. That means balls, or a ball "aimed" in the direction of `M`: it travels until it hits a monster or a wall, so it explodes on `M`.
- Choose between area and single-target by total damage, as owner 11-09 requires.
- Otherwise WAIT (`anaguma:hold`).

**Ranged from `P`.** Bolts, arrows and beams reach only `M` in the zigzag. In the I-shape they also reach the corridor line.

**Healing.**
- Potions and the existing heal rungs work unchanged.
- Rest (`R`) only when no pack member is awake within reach. Hounds in hiding are within reach, so this mostly means after the pack is gone.
- The animals' approach test uses the player's HP and SP (1.5). The long zigzag pulls them in through blocked retreats regardless of HP (1.7), so resting does not change the pull-in. It only makes the last one stay out longer, which is handled by 5.1.

**Abandon** (the existing release rules plus pocket-specific ones):
- Instant death, or T1 leave: Teleport, Recall or *Destruction* (owner 11-04 order). Not `_flee_step`.
- HP below 40% or predicted damage ≥ 50% (`_choke_engagement_key` release, `policy_combat.py:4042-4157`): Teleport.
- A `PASS_WALL` or `KILL_WALL` monster appears or is detected: leave before it arrives.
- The pocket geometry changes, for example a wall is broken by `KILL_WALL` or a quake: re-validate every turn and release on change.
- No progress in `COMBAT_OUTCOME_WINDOW` (300) decisions: release (existing budget).
- Teleported or swapped out (`TELE_TO` from the monster on `M`): the plan is released by the existing floor and plan invalidation.

**Leave when the pack is gone.**
- Leave when no pack member has been seen or detected for 50 game turns, then cast a detection if one is available (section 9).
- Then resume exploring.
- The pocket stays on the map and may be reused on the same floor at 0 digs.

### 5.1 Closing in on the last one (owner: 「最後の一匹は近寄ってこないのでこちらから詰める動きが別途必要」)

**When it applies:**
- An Anaguma plan of L >= 4 is holding.
- Exactly one member of the pack is left, seen or detected.
- That member has not stood on `M` for the last `K` of its own moves. A proposed `K` is 3; it could also be measured in stage 1.
- It is within the tunnel or within the 10-step flow radius that keeps it in hiding mode (1.5).
- The hiding mechanics put it at distance 2 or more and out of the player's projection, typically on `D`.

**What the game allows (from 1.5 and 1.7):**
- **No single-target ranged attack can reach it.** A hiding cell is by definition one the player cannot project to.
- **An area attack can.**
  - From `P`: a ball aimed in the direction of `M` explodes on `M` and covers `D` (1.7).
  - From `M`: a ball aimed toward `D` explodes on `D`, or on the animal, and covers the next tunnel cell.
- **At equal speed a melee chase does not catch it inside the tunnel.** Simulated with the same port: the player steps out and follows, at one move per animal move.
  - The animal keeps backing off to distance 2 while hidden cells exist behind it.
  - It was caught only once both reached the open corridor, where it had no hidden cell left and the surrounding decider took over.
  - With 2 player moves per animal move, the player was adjacent on its first move.
  - In a real map, corridors bend and offer hidden cells, so the chase may not end there.

**Proposed close-in move, in order:**
1. **Area attack from `P`**, when the last one is on `D` and the bot has an area attack: absorbed balls, ball wands or rods, *Destruction* excluded. It is chosen by total damage as in owner 11-09. No exposure is added.
2. **Haste, then step out and strike.** If the player is faster than the animal, or can become faster with a speed source the tiers count as free (the owner's 11-04 Magic-Eater absorbed-speed rule): step to `M`, then attack the animal on `D` before it moves.
3. **Bounded chase.** Otherwise step out and follow it along the tunnel toward the corridor.
   - Melee whenever it is adjacent on the player's turn.
   - Use an area attack whenever one covers it.
   - **Limit:** stop at the tunnel's corridor end, or (decision 「出口まで追う」, section 9). Never follow it into an unexplored area or toward other awake threats.
4. **Otherwise disengage.** Leave the pocket and resume. A lone pack animal is left to the ordinary ladder: hunt, flee, the tiers.
   - A lone hound can still breathe at the cells next to the player from hiding (1.2). The ordinary ranged and threat rules cover that.

**Safety while closing in:**
- Once the player leaves `P`, the cell is no longer a pocket. The usual release rules apply: instant death, T1, HP 40%.
- Other packs that arrive meanwhile restart the Anaguma plan at the existing pocket, which needs 0 digs.

---

## 6. Per class: means and stock

| Class (bots in use) | Means today | Gaps |
|---|---|---|
| Warrior (n1-a, n1-b) | **Wand only**: `_stone_to_mud_wand` / `_has_charged_stone_to_mud` (`src/hengbot/policy.py:13733`, `:13742`), cast via `item_reservation.reserved_item_command` (`src/hengbot/item_reservation.py:483`, `a` + letter + direction) | The Rod of Stone to Mud (tval 66, sval 29) is never aimed. There is no `SV_ROD_*` constant; it is only in `me_device_policy.json:1097`. A rod gives unlimited digs (with recharge time) and would make Anaguma cheap. Warriors' device skill is low: use `p_success` from the bot's existing device-fail estimate. |
| Magic-Eater (n1-c) | Wand, plus the absorbed wand (`me_capability.py:273` `Replacement(("wand", SV_WAND_STONE_TO_MUD), …)`, cast with `me_absorbed_substitutes.carry_cast_key`, `me_absorbed_substitutes.py:120`; key `m` + kind + letter + direction) | An absorbed rod is not supported. Absorbed charges recharge over time: count them as the cheapest source. |
| Arcane or Nature casters, Half-Giant, activations, Sniper, Samurai | Not used by the bot | Out of scope until such a bot exists. Listed for completeness (1.1). |

**Stock rules.**
- Owner 10-20: keep every Stone to Mud wand, charged or empty (`policy_home.py:2693-2703`). Buying rungs exist (`policy_shop.py:218`, `:2863`, `:3078`).
- Quest 2 (Q2) needs 2 charges (`Q2_BREACH_WALL_COUNT`, `policy_constants.py:741-746`).
- Decision 「資金に余裕があるとき魔法棒を塔でチャージする」 (section 9): no new buying; the Tower recharges the carried wands.

---

## 7. Implementation plan (stages)

Each stage is its own commit, and each passes the existing suite and lints.

**Stage 0 — geometry module.**
- New `src/hengbot/anaguma.py` with pure functions:
  - `pocket_cells(grids, s, orientation)`, templates from 2.2;
  - `is_pocket(grids, p)`;
  - `concealed(grids, p, m)`;
  - `follower_reach(grids, m)`, via `projection_path.projection_path` and `quest25_geometry.los`;
  - `dig_order(...)`, the 8-direction zaps;
  - `candidates(snapshot, hostiles, budget)`.
- Unit tests on constructed maps (marked DECLARED CONSTRUCTED). They pin:
  - the table of 2.2: notch = 3 open; I = 1 shooter; zigzag L = 3 = 0 shooters with reach 3; room I = 40;
  - the zigzag at L = 4 to 8: 0 shooters, reach `{D}`, a ball on `M` covers `{P, M, D}`.
- Port the hiding chain of 1.7 (`anaguma_sim.py` in the scratchpad) as a test helper, not as policy code. Pin "zigzag L >= 4: N - 1 animals reach `M`; L = 3: 3 stay out".

**Stage 1 — record only.**
- Compute the best candidate at every trigger from 3.1 and log `anaguma:candidate` (with digs, `T_dig`, `T_arrive`, concealed, and the veto reason) in the decision record.
- Take no action. Run it on the captures in section 8 and on live boards for a day.

**Stage 2 — dig and hold, for non-animal packs.**
- Add `_anaguma_key` in pre-combat before `_choke_engagement_key`, with `ChokeEngagementPlan` phases `dig` and `hold`.
- Wand and absorbed casting reuse `sealed_pocket.melt_at_key`-style key building (`sealed_pocket.py:265`).
- Re-validate after each dig.
- Register the ladder row, reasons, claims and the `_forbid_wait_while_damaged` allowance.

**Stage 3 — fighting in the pocket.**
- Area attack at `M`.
- Half-damage redirected-blast term in `threat_prediction` and `threat_tiers`.
- Abandon rules from section 5.
- The summoner rules stay first.

**Stage 4 — means.**
- `SV_ROD_STONE_TO_MUD` aiming (`z` + letter + direction).
- Charge reserve (section 9).
- The Tower recharge of carried wands (section 9).

**Stage 5 — animal packs**, per the owner's answer (1.7):
- minimum L = 4 for `ANIMAL FRIENDS` packs;
- dig longer, up to 8, while terrain, time and charges allow;
- the last-one close-in of 5.1 (section 9).

---

## 8. Tests: recorded pins

Pack incidents found in `C:/hengband-backups/pdca/captures`:
- Snapshot lines carry `grid_map` and `visible_monsters`.
- Gzip tails need member-wise decoding (`zlib.decompressobj(31)`).
- Fixtures go in `tests/fixtures/` with an `extract_<topic>_fixture.py`, following `tests/test_detected_pack_no_choke_recorded.py` (state-line replay) or `tests/test_summoner_hold_los_1102_recorded.py` (single board).

| Capture | Pack | Stone to Mud | Pin |
|---|---|---|---|
| `stops-1104-morning/n1-b/life-306/incident-captures/20261104-015401-player-death` (Angband 19F) | cave orcs, up to 10 at once (`FRIENDS`, not `ANIMAL`) | wand, 7 charges | **Main positive pin.** At the first frame with 4 or more orcs (turn 4830511), stage 1 logs a concealed candidate and stage 2 issues the first zap. Later frames: hold, one attacker. |
| `n1a-504-death-1110/incident/20261110-011720-player-death` (Angband 24F, RQ41) | air hounds ×4 (turn 878346), light hounds (turn 882045), fire hounds ×10 plus phase spiders (turn 897005) | wand, 2 charges | Animal-pack pin. With only 2 charges, the minimum L = 4 for animals cannot be dug, so the expected decision is **no dig**: the existing behaviour, a veto with the reason `anaguma:charges`. A constructed variant with 6 charges (marked DECLARED CONSTRUCTED) expects a 4+ cell zigzag. |
| `latest-12h-1031/n1-a/life-446/incident-captures/20261031-060729-player-death` (Angband 48F) | 窖に潜むもの ×17, Mirkwood spiders ×13, gargoyles, fire trolls | wand, 14 charges | Mixed pin. Check `PASS_WALL`/`KILL_WALL` and breathers in the pack; this checks the veto paths. |
| `stops-1104-0750/n1-c/life-126/.../20261104-072847-player-death` (Yeek cave 1F) | jackals ×49-53 plus breeding mice | none | Negative pin: no means, so no dig and the existing behaviour is unchanged. Jackals are spell-less `ANIMAL FRIENDS` (1.5). |
| `me-dual-wield-1101/n1-c/life-096/rest/.../20261101-173135-player-death` | jackals ×9 | none | Negative pin, as above. |
| `fix-deaths-1101/n1-b/life-285/.../20261101-005823-player-death` | giant white mice (breeder) | none | Negative pin, breeder. |
| `deaths-1109/life-355` (Angband 80F, Chiron locusts ×13) | — | wand, 8 charges | No snapshots were copied, so it is not pin-ready. Keep it as a stage-1 log check if a new capture appears. |

These existing pins must stay green:
- `tests/test_detected_pack_no_choke_recorded.py`
- `tests/test_choke_hold_loop_recorded.py`
- `tests/test_choke_stall_recreate_1108_recorded.py`
- `tests/test_summoner_avoid_narrow_1102_recorded.py`
- `tests/test_sealed_pocket_quest_1105_recorded.py`
- `tests/test_quest_sealed_pocket_1108_recorded.py`
- `tests/test_breeder_swarm_1102_recorded.py`
- `tests/test_threat_tiers_*_recorded.py`

A **live check** through the control server (`tools/bot/hbctl.py`, debug `^A`) is needed for stage 2:
- summon a cave-orc pack and a fire-hound pack next to a granite corridor;
- confirm the dig order, the single-file queue, and the half-damage breath at `M`;
- confirm the hounds' hiding behaviour in 1.5;
- **confirm the owner's mechanism of 1.7 in the real game**: a jackal pack and a hound pack, a zigzag of L = 3 and of L = 6, and the count of animals that step onto `M` versus stay hidden. The Python port is not the game; for example, turn order and energy randomness are simplified.

---

## 9. Owner decisions (2026-11-10, all questions answered; locked spec)

Verbatim, with the reading the implementation follows:

| Topic | Owner (verbatim) | Implementation |
|---|---|---|
| Animal packs | 「動物の群れにはジグザグの通路を長めに取る。すると、動物の後退する動きが後続に阻まれ順に近寄ってくる。最後の一匹は近寄ってこないのでこちらから詰める動きが別途必要になる。」 | The zigzag of 2.3; the minimum length for an `ANIMAL FRIENDS` pack is 4 (1.7) |
| Last animal | 「範囲→加速→出口まで追う　を基本的には採用するが、加速は魔道具術師など消耗品を使用しない場合に限定する」 | 5.1 in this order: an area attack from `P` into `M`; haste only by a non-consumable means (the Magic-Eater's absorbed Speed, never a potion), then step to `M` and strike; chase up to the tunnel's exit; then the ordinary ladder |
| Length | 「4マス/2マスを基本とし、地形と岩石溶解の回数が許すなら8マスまで伸ばす」 | Base 4 (animal packs) or 2 (others). Extend one cell at a time up to 8 while the terrain (known diggable rock, 2.4) and the charges allow. The arrival budget (3.3) decides when to stand on the innermost cell |
| Charge reserve | 「魔道具術師の場合は自然回復するので残さなくて良い。それ以外なら1回残す。」 | Magic-Eater: no reserve. Every other class: 1 charge kept |
| Ranged and breathers | 「常に使う。通路など、通常地形よりは明らかに被弾回数が減るからである。高威力攻撃を持つ個体は通常の生存ルーチンで対応する。」 | No damage gate of its own. The survival rungs above it (emergency, instant death, one-shot breath, resistance, summons, *Destruction*) answer the high-damage individuals |
| vs an existing choke | 「掘れるなら掘る」 | Dig whenever the charges and the arrival budget allow; otherwise the existing choke rungs act as today |
| Summoners | 「使う」 | Used; the summon rules (11-04, 11-06) stay above it |
| Abandon line | 「今の基準のまま」 | The existing flee test (`_should_flee`) releases the plan. In the pocket the escape is *Destruction*, then the escape scroll; walking out is never chosen |
| Waiting | 「50ゲームターン。待った後、可能なら感知を使って状況を把握する。」 | A hold with no pack member in view for 50 game turns ends. Then the bot casts a detection if it has one; otherwise the plan ends |
| Floors | 「ランダムクエストの階も使う」 | Ordinary dungeon floors and random-quest floors. Not fixed quests, town or the wilderness |
| Stock | 「資金に余裕があるとき魔法棒を塔でチャージする」 | No new buying. A non-Magic-Eater recharges carried Stone to Mud wands at Morivant's Tower when spare gold pays the trip, reusing the Tower steps (`morivant_tower`). The Magic-Eater's own staff sequence already charges and absorbs them |

What follows from the decisions:
- **No damage gate.** The pocket rung itself never declines a pack for its ranged damage (decision "常に使う"). It declines only for:
  - a monster that passes or kills walls;
  - no charge;
  - no time;
  - no diggable terrain;
  - a fixed quest, town or the wilderness.
- **One escape path.** The rungs above it still preempt it when they apply.

---

## 10. Implementation notes (2026-11-10)

Code:
- `src/hengbot/anaguma_geometry.py`: the zigzag of 2.3.
- `src/hengbot/anaguma.py`: the rung (`dungeon_ladder` floor-avoidance layer, before `_detected_threat_preparation_key`).
- `src/hengbot/wand_tower_recharge.py`: the stock answer.

What the code does where the design left a detail open:
- **Unknown rock.** From a corridor the board shows only the first layer of rock. A plan presumes unknown grids to be rock. Each cell is checked again when it opens or is about to be melted. When the presumption fails, the player holds on the cell where it stands if that cell is a pocket; otherwise the plan ends (`dig-refused`).
- **The pack.** Two or more hostiles of one `FRIENDS` race (not `NEVER_MOVE`), in view or detected, with at least one awake. Breeders that are not `FRIENDS` are left to the breeder rules.
- **No plan is started** in these cases:
  - a pack member is already adjacent;
  - the existing flee test (`_should_flee`) already leaves;
  - any hostile on the board passes or kills walls;
  - the usable charges are below the base length.
  The start cell is within 8 walking steps and no closer to the pack than the player is now. The arrival time is the nearest awake member's path length to the start cell (unknown grids count as floor) divided by the fastest member's moves per player move.
- **Waiting.** In the hold, the 50 game turns restart on every contact: a monster on the mouth, or a hit taken. After them, one detection is tried:
  - a carried rod of Detection;
  - a staff of Detect Evil, for an evil pack;
  - the absorbed power of either.
  Then:
  - an animal pack with exactly one member known gets the close-in;
  - members still known get one more wait of 50 game turns;
  - otherwise the plan ends.
- **Close-in.** The area attack is an absorbed or carried ball or breath aimed in the direction of the mouth, whose blast reaches the animal (`breeder_area_attack` geometry). The haste is the Magic-Eater's absorbed Speed only. The chase moves outward along the tunnel and ends on its start cell.
