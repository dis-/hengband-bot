# Ammunition fitting verdict (2026-10-01)

Step 1, base `275841d3f53ee07e92c22098a776bc8b17675714`.

User decision: 「重量に収まる個数までしか買わない」; normal dives top up
to the smaller of 99 and the count fitting the weight limit. Deposited ammunition
stays at Home; fixed-quest entry still requires 99.

The board loaded at tests/test_shop_one_shot.py:833-835 is
tests/fixtures/24-town3-reward-pack-full-stop.json:1, turn 2866604.
Printed inspection gives floor `(0, 0, 0)` and both
`_carry_procurement_strategy` and `_quest_strategy_for_errand_or_floor` as `None`:
this is normal-dive procurement, not a fixed-quest entry.

Printed kit: pack slots a/b mushrooms; c/d/e speed/cure-critical/healing potions
(6/11/5); f/g/h/i teleport/recall/identify/remove-curse scrolls (38/10/2/1);
j rod, k/l wands (3/1), m identify staff, n cloak, o axe, p two shovels;
q/r/s/t/u/v/w bolts (10/14/27/13/5/12/18), each weighing 3.
Equipment: lance 300, crossbow 110, rings 2+2, lamp 60, robe 20,
cloak 0, boots 20. Equipment totals 514; pack totals 992; carried weight 1506.

src/hengbot/policy_helpers.py:290 sums all pack and equipment weight.
src/hengbot/policy_home.py:1105 derives limit 1700 from strength index 28
(class 0). The selected ammunition plan reserves w=18 and q=10, total 28;
other carried ammunition remains included in weight, not assumed deposited.
The synthetic ware at tests/test_shop_one_shot.py:837 has weight 0 (unspecified);
src/hengbot/policy_home.py:1154 falls back to q's observed unit weight 3.
Room is 1700-1506=194. Buying floor(194/3)=64 adds 192, ending at 1698.
The target is min(99,28+64)=92; the shortage is 92-28=64.
Buying the old 71 adds 213, ending at 1719, exceeding the limit by 19.
The temporary removal/re-addition of reserved ammunition in the target
calculation cancels exactly: 194+84-84=194. No purchase is counted twice.
No future purchases or deposits are assumed by this direct component test.

Verdict: 64 is correct. Change only the explicitly authorized expectation
at tests/test_shop_one_shot.py:849, with the decision and arithmetic in a comment.
Do not change production code, other assertions, fixtures, or EXPECTED_FIRST.

Step 1 assertion audit: `No changed pre-existing assertions or forbidden test edits.`
