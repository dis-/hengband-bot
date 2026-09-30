# Live8 fixes

Worktree: `C:\hengband\bot-client-decl-r3b`, branch `decl-r3b`, base `92c5f533`.
Recorded evidence: `incident-20260930-1932-s33-live-one-shot-in-flight-after-calibration-strip` decisions/state/ownership logs and its stdout log (read only).

## 1. Calibration restore

Cause: the Home plan stop authorized equipment-txn/home-visit, while the plan gate at `src/hengbot/policy.py:5860` refused calibration. Recorded decisions 207 and 209 explicitly defer `_calibration_town_key`; 211 still has calibration phase `deposit`, with an empty pack. Therefore calibration never advances its phase or runs the restore scan in `src/hengbot/policy_calibration.py:1262`. Deposits invalidate the Home address space, leaving the still-filed calibration-restore request addressless. The Home-page fallback at `src/hengbot/policy.py:8685` reports `home-knowledge-invalidated` on 212. Its ESC is a page exit, not a persistent stop: unrelated restocking follows on 213. The ad0c1303 debt preservation did not solve this scheduling refusal; the identities remain owed.

Fix: `src/hengbot/policy.py:6496` stops with `ownership:declaration-unrestored:calibration` when the plan defers calibration with restoration debt and no pending Home atomic operation. Survival/bookkeeping exemptions remain available. The debt and phase survive the stop. This implements the explicitly permitted visible-stop outcome; it does not claim to perform automatic recovery or a Home rescan in this blocked-plan case. Existing permitted calibration execution still owns its ordinary scan/restore path.

Pins: `Live8RestoreTest` in `tests/test_live8.py`: recorded 207-212 facts; production plan gate followed by the result seam, both fresh and pickle-restored; OFF retains the recorded key. Single source revert produced the expected assertion failure (`'5' is not None`).

Commit: `99374547`.

## 2. Empty one-shot wait

Cause: the attempted purchase was two Identify staves, Magic shop/store 5, shelf j (`鑑定の杖 (2x 17回分)`, price 926 each), tail `pj2\r\r\x1b`. Decision 219's saved visit instead targets Home/store 7, opened sequence 219, posted sequence 218. The composer at `src/hengbot/policy_shop.py:4987` consumes the saved ordinary-shop page while mutating the current visit; composition at `:5031` sets operation_posted before actual tail dispatch. Row 220's claimed observation identity is `[219, 7, "pj2\r\r\x1b"]`, its current visible page is store 5, and execution is null. This is not a valid posted purchase observation.

The in-store posted-operation branch at `src/hengbot/policy.py:9575` returns an empty key merely from the posted flags. The old result gate only checked the empty `store:entry-await-observation` reason; shop-buy family agreement let this different empty wait through. The pending purchase tail was not the emitted command at 219: stdout shows only `5`, then `<no-key:shop:one-shot-in-flight>`. The driver reports no new snapshot within its existing 1.5-second bound. The logs establish that stalled dispatch and timeout; they do not establish a transport failure.

Fix: `src/hengbot/policy.py:6514` requires the live visit identity, unobserved effect, matching store context, matching Observe goal, and an awaiting execution declaration bound to that visit's posted sequence and command. A valid wait explicitly offers the same typed observation declaration. An absent or inconsistent declaration yields `ownership:declaration-stale:<family>` before an empty key can escape. No timeout or budget was added.

Pins: `Live8OneShotTest`: recorded 220 mismatch; valid awaiting observation and five invalid cases (missing declaration, stale sequence, wrong store, changed identity, already observed effect), each fresh and pickle-restored. Single source revert produced the expected empty-key assertion failures.

Commit: `5daadbec`.

## 3. Progress rewrite

Cause: procurement's progress composer called the purchase producer directly (`src/hengbot/policy_town.py:978`), bypassing the town entry/plan gate. This explains why row 219's ledger defers `_atomic_shop_transaction_key` but a purchase is nevertheless composed downstream. The final replacement at `src/hengbot/policy_town.py:1348` labels the result as detectors and has no matching purchase declaration. S3.3's public holder refusal already exists, but the direct procurement seam did not preserve a holder's key and reason itself.

Ruling #5 review item 4 requires a live holder's own key to pass through unchanged. Row 219's restock Terminal is not itself an open held Observe; its additional concrete defect is bypassing the next Home plan stop during composition.

Fix: `src/hengbot/policy_town.py:1113` checks the selected holder first, records procurement rewrite refusal, and returns the original key and reason before composition or visit mutation. `:978` now runs the purchase composer through `_town_producer_entry` with the shop family, including plan gating. OFF uses the original producer behavior.

Pins: `Live8RewriteTest`: recorded 219 rewrite/store mismatch; holder key/reason preservation fresh and pickle-restored; purchase composition cannot bypass a Home plan stop. Single source revert produced a holder-return assertion failure and absent-gate evidence.

Commit: `ef071d3d`.

## Verification

Each test module ran in its own process, with `PYTHONPATH=src;tests;scripts` and the real Python 3.13 interpreter.

| Allowed check | Result |
| --- | --- |
| tests.test_live8 | 8 passed |
| tests.test_declarations_r11 | 10 passed |
| tests.test_test_fakery_lint | 13 passed |
| tests.test_town_progress_invariant | 22 passed |
| tests.test_calibration_crossarea_debt | 5 passed |
| stuck s33 first-divergence fixture | OFF hash matched; no divergence; no trajectory defect |
| withdraw s33 first-divergence fixture | OFF hash matched; exact unchanged expected first difference at index/sequence 20, `shop:travel`; no trajectory defect |
| Per-task single revert checks | Each exposed its regression |

Both fixture measurements have zero ON gate-final leaks, no declaration-gap rows, and no declaration mismatches. Existing detector-family missing declarations remain reported by the measurement (one per fixture); they are outside the measured town declaration families.

Only two production modules changed: policy.py and policy_town.py. No new durable attributes, thresholds, or EXPECTED_FIRST edits. No live bot/game/exe operations, gate scripts, forbidden test modules, or long fixture runs were performed. The new pins are focused production-seam tests plus recorded-row facts; they are not a continuous replay of the live8 incident, and no live recovery is claimed.
