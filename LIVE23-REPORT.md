# Live23: recorded Home catalogue / digger alternation

Baseline: `ca369103`; branch `decl-r3b`. Source capture is read-only.
The fixture provenance records source hashes and exact state line indices.

## Step 1 — recorded evidence before implementation

(a) Entry succeeds. Decision 1972 sends `5` at (45,123), turn 670848;
state line 2263 (zero based) is a Home page with 24 items, stock_num 24,
page_size 52. `policy_shop.py:4851-4873` intentionally activates the entrance
with `5`. `policy.py:7274-7326` takes the early catalogue acquisition path
because the nearly full pack has invalidated Home knowledge. Its execution
expects `home-catalog-available`, but `policy.py:4251-4267` completes the
store-entry claim merely because the page opened. Thus it enters repeatedly,
rather than failing to enter.

(b) `policy.py:8761-8775` calls `_queue_standing_home_digger` before adopting
the complete observed catalogue. `policy_equipment.py:506-534` requests two
diggers regardless of departure purpose, binds one, and sends ESC. The
recorded fundraising mode is None throughout 1962–1975: this is ordinary
exploration, so this withdrawal is unwanted under the user's mining-only rule.
The invalid catalogue remains invalid, restarting the entry path.

(c) Home deposit claim 1656 completes at 1972 (`home-deposit-observed`).
Equipment claim 1657 then registers catalogue acquisition before home-visit
claim 1658 at 1973. The latter gets the decision because the Home branch
does not continue catalogue acquisition and entry completion drops 1657
before a producer's claimed effect (`home-catalog-available`) was observed.
Claims 1659/1660 repeat this at 1974/1975.

(d) `_record_decision_claim`, `policy.py:4354-4373`, completes the prior claim
before `_s33_shadow_verdict` sees it. At 1973, 1657 has closed; the shadow
has no standing holder. `policy.py:4932-4939` fills an absent shadow holder
with the newly declared actor (1658, home-visit). Likewise the next cycle
uses equipment-txn. ON calls the same premature completion before entry
gates (`policy.py:2703-2711`), so registration order cannot protect the work.
The holder must remain the registered catalogue work until its evidence is
observed or it releases by name; entry is a step, not that work's completion.

Existing untracked `.live8b-revert.py` was present before this task and is untouched.

## Verification restrictions

The inherited DO NOT RUN block forbids `tests.test_absorbing_states` and
all town producer purity parts; these remain pending for Claude. The live23
instruction explicitly permits the stuck/withdraw OFF+S3.3 fixtures. No live
bot, game, other worktree, or runtime/jsonlog file is changed.
