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
