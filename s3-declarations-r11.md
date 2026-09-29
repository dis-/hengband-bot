# Declarations r11

Implementation commit: `d49a72f7`.

| Review item | Implementation | Pin |
| --- | --- | --- |
| 1 Entry gate | `src/hengbot/policy.py:5785` wraps 76 `_decide` rung calls and the direct town composers in `_choose_key`; it skips competing families before invoking them. | `tests/test_declarations_r11.py:24` |
| 2 Result leak | `src/hengbot/policy.py:6376` counts OFF `final:` rows and makes an ON leak `ownership:gate-missing:<family>`; `scripts/first_divergence_s3_3.py:138` reports the count. | `tests/test_declarations_r11.py:40` |
| 3 Retry | `src/hengbot/policy.py:2716` uses the same Home capture path on both passes and stops retrying after a leak. | `tests/test_declarations_r11.py:57`; `tests/test_crossarea_fundraising.py:123` |
| 4 Held key | `src/hengbot/policy.py:5832` compares the selected reason family with the holder; no-progress, procurement, and arbiter retirement record `rewrite_refused`. | `tests/test_declarations_r11.py:79,92` |
| 5 Other rewrites | `src/hengbot/policy.py:6438` excludes bookkeeping and detectors from the errand result check. | `tests/test_declarations_r11.py:113` |
| 6 Store scope | `src/hengbot/policy.py:6376` treats an open store page as town even when `in_town` is false. | `tests/test_declarations_r11.py:128` |
| 7 Plan order | `src/hengbot/policy.py:5825` gates families outside the current plan stop's requester set; dungeon boards bypass the town gate. | `tests/test_declarations_r11.py:138`; `tests/test_ownership_s3_3_first_divergence.py:28` |

Each item's pin failed under one temporary source revert; the original source was restored after each check. The unchanged r10 pins and four live incident pins in `tests.test_execution_declaration` passed.

The `stuck` replay has no first divergence and zero ON gate leaks. The `withdraw` replay has the exact plan-next first difference at index 20 (key `ESC + backtick + n%.`, reason `shop:travel`), zero ON gate leaks, and 20 OFF `final:` rows. Both OFF trajectory hashes match their frozen values. The remaining named unit modules passed individually; no full-suite runner or prohibited command was used.

{"topic":"declarations-r11","implementer":"gpt-6-sol","code_commit":"d49a72f7","pins":8,"revert_checks":7,"stuck_on_gate_leaks":0,"withdraw_on_gate_leaks":0,"withdraw_off_final_rows":20}
