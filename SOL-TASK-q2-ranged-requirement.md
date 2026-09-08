# SOL-TASK: Q2 ranged requirement (per-shot 25 / 99 bolts) and gremlin kill priority

**USER DECISION (2026-09-09, verbatim):**
「射撃武器の要求値をグレムリン確殺の射撃1発あたり威力25、弾数を99に変更。Q2中はグレムリン討伐の優先度を上げる。」

This is an approved SPEC CHANGE to `strategy/quests/QUEST_2.jsonc`, which is an approved profile.
It is authorized. Implement it; do not renegotiate it.

## Why 25 is the right number — the mechanic

`lib/edit/MonraceDefinitions.jsonc`, monster id 153:

```json
{"id": 153, "name": {"ja": "グレムリン", "en": "Gremlin"},
 "hit_point": "5d5", "armor_class": 30, "level": 8, "speed": 0,
 "flags": ["MULTIPLY", "IM_POIS", "RES_DARK", "HURT_LITE", "EVIL", "DEMON",
           "OPEN_DOOR", "TAKE_ITEM", "CAN_SWIM"]}
```

**5d5 → maximum HP 25.** The number is not arbitrary; it is the race's HP ceiling.

**The requirement is on the AVERAGE per-shot damage — the user settled this explicitly.**

> USER (2026-09-09, after the supervisor flagged that 確殺 read literally implies a minimum):
> 「平均25で良い。まだ不足するようなら再度調整する。」

So: **average per-shot damage >= 25**, using the same average convention the profile already uses
for its「1命中平均18点」figure. Do NOT implement a minimum-damage gate. Record in the profile that
this is an average against a 5d5 (max 25) target — i.e. it kills a typical gremlin outright and is
deliberately a tuning value the user expects to revisit, not a proof of 確殺.

## What the current loadout actually does — it cannot satisfy this even on a perfect roll

The profile's own formula (`ranged_softening`, and `shoot.cpp:492`: the bow's to-dam is inside the
multiplier):

```
per shot = (bolt dice + bolt to-dam + bow to-dam) x multiplier
```

At quest entry the character carried Light Crossbow (x3) (+2,+3) with plain Bolts (1d5)(+0,+0):

```
min = (1 + 0 + 3) x 3 =  12
avg = (3 + 0 + 3) x 3 =  18   <- the profile's stated "1命中平均18点"
max = (5 + 0 + 3) x 3 =  24   <- even a MAXIMUM roll is 24 < 25
```

Against the **average >= 25** requirement the entry loadout gives 18 — short by 7.

What the average requirement implies for gear, with a x3 launcher:

```
(3 + to_dam_total) x 3 >= 25   ->   to_dam_total >= 5.34   ->   to_dam_total >= 6
```

The entry loadout had `to_dam_total = 0 (bolt) + 3 (bow) = 3`. The (+5,+2) bolts the character also
owned give `to_dam_total = 5` → average `(3+5)x3 = 24` — still one point short, which is worth
saying out loud in the profile because it is so close. A x4 launcher needs only
`to_dam_total >= 3.25 -> 4`.

Derive and record the actual threshold yourself rather than copying these numbers — verify the
formula against `shoot.cpp` the way the existing rationale did, and state whether the STR multiplier
and criticals are in or out of your figure (the existing rationale excludes both, conservatively).

## Why 99 replaces 45

The current `throwing_items.launcher_ammo: 45` rests on a rationale that treats gremlins as static:

> 残余（ネズミ/ムカデ/ナメクジ/**グレムリン**/イモムシ/青ベトベト）は各3以下

Gremlin has `MULTIPLY`. The live run reached **9 simultaneous hostiles**, fired `q2-fire` 49 times,
and then hit `q2-close-residual-multiplier-no-ammo` **7 times** — it ran the launcher dry. 45 was
derived from a false premise. 99 is the user's decision and matches what Q22 and Q31 already
require (`QUEST_22.jsonc:56`, `QUEST_31.jsonc:65`).

## The three changes

**C1 — `strategy/quests/QUEST_2.jsonc`:**
- `required_force.throwing_items.launcher_ammo`: 45 → **99**
- add a per-shot minimum-damage requirement of **25**, in whatever field name the loader and the
  consuming code can actually read (see C2 — do not invent a field nothing consumes)
- update the `rationale` and `ranged_softening` prose so it no longer says gremlins are static and
  no longer implies 45 bolts suffice. Keep the existing derivations that are still true; correct the
  ones that are not. State that 25 is 5d5's ceiling and that the requirement is a MINIMUM.

**C2 — make the per-shot requirement actually enforced.** `required_force` currently carries
`min_expected_dps`, `speed_potions`, `heal_potions`, `launcher`, `throwing_items`,
`required_scrolls`, `utility_tools`. There is no per-shot damage concept. Find where
`required_force` is consumed (`quest_strategies.py` for loading; `_quest_launcher_ammo`,
`policy_equipment.py:737-748`, `policy_quest.py:626-705` for use) and wire the new requirement into
the same acceptance gate that already blocks the quest on missing carries. If the loader validates
`required_force` shape, extend the validation.

**C3 — raise gremlin kill priority during Q2.** `priority_targets` already contains 153, and
`engagement_plan.immediate_priority_targets` currently contains only `[270]`. The engagement plan's
`formation` already names the user's 2026-07-18 ordering (巨大白ネズミ→グレムリン→青ベトベト).
Raise 153's priority so the bot kills gremlins ahead of non-breeder work. Do NOT displace 270 —
the wererat's S_KIN summon is documented as the single worst danger on this floor and the plan says
never to switch targets while it is visible. Say exactly how you ordered them and why.

## Hard requirements

1. **AN UNMET REQUIREMENT MUST NOT STOP THE BOT.** It must flow into the EXISTING not-ready
   fallback: the bot declines to accept the quest and continues ordinary progression — explore,
   fundraise/mine, dive, shop.

   > **Supervisor correction (user, 2026-09-09):**「全てのクエスト受要件が満たせない場合は
   > ダンジョン探索か採掘に進むはずだが可視停止するのか？」
   > The user is right and the first version of this document was WRONG to demand a visible stop.
   > That fallback already exists and is exercised: over the live log there are **3,645 decisions
   > with `fixedquest_readiness.verdict = False`**, during which the bot ran `explore` 521,
   > `fundraise:dig-to-treasure` 437, `fundraise:seek-treasure` 308, `fundraise:seek-loot` 244,
   > `seek-downstairs` 182, plus ordinary shopping. It never stopped. Demanding a stop would have
   > REPLACED working behaviour with a halt.

   So pin the real thing: with the requirement unmet, `fixedquest_readiness.verdict` is False AND
   non-quest progression continues. Not a stop, not a loop. An unmet carry requirement is a normal
   state transition, not a fault. Visible stops are for states with no bot-reachable exit (the Home
   deferral absorbing state was one); this is not one.

   The one genuine risk is an UNBOUNDED shopping cycle — the bot circling town forever trying to buy
   what it cannot afford or find. Check that the existing town progress invariant already bounds it,
   and say what you found; do not add a new bound on top of a working one.
2. **The acceptance gate must be the ONLY thing that changes about quest entry.** Do not weaken any
   other carry requirement to make room for 99 bolts. If pack space or weight becomes the binding
   constraint, report it — do not silently drop another requirement.
3. **This does not repair the teleport-reset defect.** That is
   `SOL-TASK-q2-breeder-teleport-reset.md`, a separate task on the same quest. Do not merge them;
   if the ordering matters, say so.

## Interpretation history, for the record

The supervisor first read 「威力25」 as a MINIMUM, because 確殺 admits no other literal reading
against a 5d5 ceiling, and flagged the consequence (to-dam >= 8 on a x3 launcher — a materially
stronger gate). The user settled it: **average**, with an explicit expectation of retuning:
「平均25で良い。まだ不足するようなら再度調整する。」 This document was amended before dispatch.

Because the user expects to revisit the number, make it easy to revisit: the threshold belongs in
`QUEST_2.jsonc` as data, NOT baked into policy code. A later change from 25 to something else must
be a one-line profile edit, not a code change.
