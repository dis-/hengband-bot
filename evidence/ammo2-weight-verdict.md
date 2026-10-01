# Ammo2 weight verdict (2026-10-01)

Step 1 base: `2fa1831e` (ammo2 merge already checked out).

Both named tests use `WeightOverloadTownTest._snapshot()` in
`tests/test_policy_home.py`. Printed kit: a heavy statue 1*200; o bolts
99*3; p bolts 35*3; q bolts 27*3; n reward sword 1*200;
r wanted remains 1*435; equipped launcher 110 and armour 996.
Total = 200+297+105+81+200+435+110+996 = 2424.
Strength index 33, warrior: limit 1850; overload 574.

Printed ordinary candidates are a and n, each fully surplus (200 each).
Wanted remains r is excluded. After a then n: 2424-200-200=2024.
The normal two-stack 99-ammo plan keeps o=72, p=0, q=27.
Its existing ammo surplus is o=27 and p=35: (27+35)*3=186.
After that surplus: 2024-186=1838 <=1850. Therefore no reduction
below the 99-ammo plan is required by 「重量超過時に鉄弾を所持している場合、超過分を預ける。」
and 「重量に収まる個数までしか買わない」. The latter governs top-up;
the former permits only the minimum extra ammunition reduction needed after
other non-required excess. 「矢は2スタック以内で99本（並＋最高威力1スタック）」
continues to govern the ordinary carry plan; fixed-quest force remains 99.

Test 1 verdict: [14,0,27] is wrong; retain existing [72,0,27].
The old calculation subtracts ordinary surplus 400 but leaves baseline ammo
surplus 186 in weight, then incorrectly shrinks the reserved 99 to 41.
Change production retention fitting to account for removable ammo surplus
before reducing the reserved plan, and only fit retention when overweight.

Test 2 verdict: three passes is wrong; retain existing four.
Required sequence: a 1 (2424->2224), n 1 (2224->2024),
p 35 (2024->1919), o 27 (1919->1838). The faulty sequence
instead deposits o 85 after a and n, ending at 1769 with p still carried.
Both existing assertions serve as revert-proof pins. No EXPECTED_FIRST edit,
no pre-existing assertion changes, no new state/checkpoint attributes.

Step 1 assertion audit: `No changed pre-existing assertions or forbidden test edits.`

## Implementation and verification

Step 1 commit: `51f2c027`; implementation commit: `85209978`.
Production fitting now deducts both ordinary non-ammo surplus and the
existing 99-plan ammo surplus before reducing reserved ammo. Retention
fitting returns the ordinary target when the board is not overweight.
Procurement fitting and fixed-quest force accounting retain their separate
behavior. No test assertions, fixtures, hashes or EXPECTED_FIRST changed.
R9 requires LF-normalized hashes; this change introduces no hash pins.

Printed fixed result:
`reservations [72, 0, 27]`
`steps [('a', 1, 2424, 2224), ('n', 1, 2224, 2024), ('p', 35, 2024, 1919), ('o', 27, 1919, 1838)]`

Single revert check temporarily restored only the production file from the
merge base, ran the two existing pins in one process, then restored the fix
in a finally block: both failed with `[14, 0, 27] != [72, 0, 27]` and
`3 != 4` (exit 1). See `ammo2-revert-check.txt`.

Exactly the requested seven modules were verified, one module per process,
with PYTHONPATH=src;tests;scripts. The initial Home run used installed
Python313; the final Home run uses the Codex runtime, as do the other six.

| Module | Tests | Result |
| --- | ---: | --- |
| tests.test_policy_home | 184 | Only the expressly excluded production executor atomic-deposit failure; 4 skipped |
| tests.test_shop_one_shot | 53 | OK, 1 skipped |
| tests.test_live36_weight | 7 | OK |
| tests.test_classC2_departure_recorded | 9 | OK |
| tests.test_ammo_surplus | 4 | OK |
| tests.test_quest_ammo_not_bought | 8 | OK |
| tests.test_test_fakery_lint | 13 | OK |

Conformance: shop-one-shot preserves the fitting top-up (64 buys at unit
weight 3, total 1698 <=1700); recorded Class C2 preserves minimum residual
deposit (1768-4*5=1748 <=1750), next-visit fitting purchases and Home stock
remaining deposited, and fixed-quest measured 95/required 99/not ready.
Live36's rejected-staff case preserves minimum six-ammo shedding.
Ammo surplus preserves the plain/highest two-stack selection. Existing
overweight candidate ordering and bounty protection remain unchanged
(the printed a,n,p,o sequence is the proof for these two subject tests).

Recorded tests print first divergent live/replay keys, including Class C2
live `1` / town:blocked:departure-unsatisfiable versus replay `5` /
town:unsafe-recall-fallback, and quest turn 3025849 live travel versus replay
one-shot-buy. No later recorded board is claimed as an effect of a new key.

Step 2 assertion audit: `No changed pre-existing assertions or forbidden test edits.`
`git diff --check` also passed. No changes to live game/bot, jsonlog,
other worktrees, thresholds or persistent state.
