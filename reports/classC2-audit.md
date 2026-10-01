# Class C2 step 1 (e8824223)

Recorded case: `incident-20261001-1616-departure-unsatisfiable-3`, final
decision 11411, turn 1493887. The work is confined to bot-client-c2.

## Answers

1. **It still stops.** The frozen outside-board attachment at the public
   `choose_key` entry prints `'1' town:blocked:departure-unsatisfiable`, with
   exactly `inventory_weight_ready` and `recall_landing_not_guardian_blocked`
   failed. Both e8824223 and the live b24fd077 content are checked explicitly
   in the step 2 single-revert experiment. This is a recorded seam, not a
   recreation of the entire 11,411-decision session: the capture lacks a
   pre-decision pickle and the catalog. The fixture attaches real Home/skill
   knowledge, shelves, purchase quantities, conquest latch, and ledger; the
   optimizer runs normally, with the run's calibration. No gate is mocked.
   The calibration's file modification time was 14:19:18 (before this run),
   and the confirmation file was 16:16:26 (before the stop); both were frozen.

2. **1983 -> 1768, limit 1750: 18 excess remains.** Decision 11398's actual
   key is `dkdjdd\x1b`. The exported boards identify k as the pick (150), j
   as the shovel (60), d as the phase-door scroll (5): reduction 215. The
   post-deposit inventory contains no ordinary surplus. Actual retention is
   oil 5, cure-critical 10, healing 3, teleport 15, recall 10, light 6,
   stone-to-mud wand 1 (MANA-food reserve), ammo 99. Identify staff h has
   count 5, per-device charges 4, total 20; its nominal zero stack reservation
   is not permission to deposit it, because no staff can be removed while
   preserving 20 charges. `_overweight_home_deposit` returns None.
   Authority: `policy_home.py:1131-1276` (safe selector),
   `policy_home.py:778-1050` (retention), `policy_supply.py:511-581` (charge
   preservation). The Home has 61/240 entries, so it is not full. At the
   stop the deposit producer has no candidate, rather than an unoffered
   deposit or a rejected deposit operation.

3. **Yeek cave 12 is guardian-blocked; an alternate exists but is unoffered.**
   `_conquest_committed` and `_target_dungeon_id` are 2. The real guardian
   predicate refuses landing (2,12). The real alternate picker with
   `guardian_bounced_dungeon=2` selects dungeon 3, Orc cave 18, which is
   deeper, has no missing depth abilities, and is not guardian-blocked.
   `policy_town.py:5157-5176` delegates to the existing fallback;
   `policy_helpers.py:324-429` admits deeper guardian alternatives;
   `policy.py:13723-13760` commits the selected target. However, the only
   town recall invocation is inside `departure_ok` at
   `policy_town.py:5556-5683`. Residual weight prevents entry, and the generic
   terminal at `policy_town.py:5726-5769` stops first.

4. **The Home cycle was catalog work, not a failed deposit.** After the
   successful deposit, knowledge is invalidated. On incomplete open Home
   pages, `policy.py:8979-9038` chooses ESC to leave before a full knowledge
   scan (the recorded requests are absent). Outside, the equipment-catalog
   need routes back to Home; 9 approaches the entrance, 1 backs out to the
   adjacent outside operation context, and the same incomplete page is
   reopened. Three no-effect passes exhaust the ordinary Home bound
   (`policy_town.py:3723-3768`). The ledger blocks Home with unsatisfied
   passes 3, visits 7, approach failures empty. Subsequent optional shop
   pages are observed and left; the final failed weight leaf has no deposit
   need. No successful deposit is reclassified as a failed operation here.
   Screen classification and modal continuation require no change (R2).

## Decisions and implementation boundary

From memory `overweight-handling-policy.md` (2026-09-03):
「まず、重量を原因に要求物資を緩和してはならない」;
「重量超過した場合の対処について。まず要求物資の過剰分を自宅に預け入れる。現状の場合帰還27テレポート45は過剰。」;
「本当に預け入れに失敗するならそれは停止するべき事案である。町中で自宅への接近が不可能になるのは正常ではない。」
From `guardian-bounce-alternate-deeper-ok-decision-20260925.md`:
「倒せない階でなければ深くても可」; with no candidate 「見える形で停止する」.

Do not invent a weight relaxation or deposit required supplies. Offer the
existing guardian switch once outstanding procurement/deposit producers have
no step, before the unsatisfiable verdict. Switching alone posts no recall;
the next real board must re-evaluate every departure gate and any newly
available surplus. Stop at the first changed key (R4); do not treat later
historical boards as effects of the switch.

changed_preexisting_assertions: []

assertion_audit (verbatim):

```
No changed pre-existing assertions or forbidden test edits.
```
