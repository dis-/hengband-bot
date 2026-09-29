# S3.3 producer declarations, round 3b

This round remains record only. A producer offers a plain-data outcome at its
return; claim exit binds only an offer from the final claim owner with the final
key. Offers for `None` are ordered against no-step and done outcomes, so a later
producer result wins. A posted, identity-bound observation wait is retained
when a later producer returns no key. The driver remains the only code that
turns an emitted command into a posted wait.

## Assigned-family audit

| Family | Sites inspected and changed | Every admitted return declared? |
| --- | --- | --- |
| equipment-opt | `policy_equipment.py` `_prepare_equipment_optimization`: context refusal, in-flight session, calibration prerequisite, retired loadout, cache, timeout, replanning and fresh search | **Yes for that producer**. It returns a preparation or `None`, so its offer binds only if the final claim and key are equipment-opt / `None`; a subsequent transaction key belongs to equipment-txn. |
| equipment-txn | `policy.py` session installation and prepared action (prior round); `policy_equipment.py` `_equipment_transaction_town_owner_key` | **Partial**. Home and ordinary town executor exits, stalled/invalidation exits in `policy.py`, and some `None` paths still lack producer outcomes. |
| calibration | `policy_calibration.py` `_calibration_town_key`: all direct key/`None` returns, including deposit and restore handoffs, aborts, scan, strip, capture and travel | **Yes for the direct key producer**. The other decorated calibration helpers return booleans rather than keys. The Home executor's own operation outcomes remain in its separate family audit. |
| departure | `policy_town.py` `_dungeon_recall_confirmation_key`, `_return_to_town_key`; stair posting in `policy_navigation.py` already declared | **Partial**. Town recall and departure branches in `policy_town.py` / `policy.py` still need a complete return census, and pass-through outcomes of `_suppress_pending_stair_command` rely on the originating producer's offer. |
| fundraising | `policy_fundraising.py` `_leave_fundraising_floor`, including recall, ascent, every route/search/tunnel branch and terminal wait | **Partial**. `_fundraising_key` and mining closure, tunnel and tapped-out helpers still have key/`None` exits without their own offers. |
| bookkeeping | `policy.py` skill-exp request, periodic save and character dump | **Yes for selected bookkeeping work**. Save/dump pass-through returns preserve the prior producer's key and owner. |
| survival / town:kill-mob | `policy_town.py` `_town_kill_mob_key`: friendly attack, approach, last-known pursuit and all no-step exits | **Yes for town:kill-mob**. This row does not claim the other survival producers. |
| identification | `policy.py` `_verified_destroy_key`; `policy_equipment.py` `_town_equipped_identification_key`; `policy_town.py` `_town_device_processing_key` | **Partial**. Home source filing and other identification flow entry points remain to be audited against final claims. |
| curse-enchant | `policy_town.py` `_town_remove_curse_key`; `policy_equipment.py` `_town_enchant_launcher_key` | **Yes for both direct producers**. |
| cross-town | `policy_shop.py` `_cross_town_shopping_key`; `policy_quest.py` `_morivant_full_identify_key` | **Yes for both direct producers**. Morivant Home phases declare an acting handoff; observed completion declares done. The store-router teleport executor is a different family. |
| rumor | `policy_town.py` rumor block in `_town_special_key`: supply/fund waits, approach, batch, and unavailable route/step | **Yes for the rumor block**. |

**Zero undeclared is not achieved.** The Partial rows above are the remaining
gaps. No design decision is identified as impossible to declare: these are
unimplemented return paths, not a request for a new policy ruling. In
particular, neither a family inferred from `last_reason` nor a generic
declaration at claim exit would close them truthfully.

## Verification and limits

`tests.test_declarations_r3b`: 12 passed. Each of the eleven family class pins
failed when its selected declaration write was suppressed once. Existing
`tests.test_execution_declaration`: 9 passed. `tests.test_test_fakery_lint`: 13
passed after replacing five collaborator-heavy pins with real fixtures or
narrow branch setup. The forbidden replay runners, gate scripts, full suite and
town producer purity modules were not run. Consequently this round does not
claim OFF replay identity or S3.3 ON replay equivalence.

Commits: `3aa2911a`, `2f102335`, `39fbbcd0`, `a44e4f57`, `64f9e2e3`,
`38984062`, `0b50fe40`, `7b70e896`, `20a58b14`, `d0656612`, `745b73d7`,
`ca709671`, `44b8e402`, `95f2eb25`, `908ce3a3`, `ff3e30bc`, `2239c075`,
`cc983233`, `9a3baa64`, `a9be3382`.

{"topic":"declarations-r3b","implementer":"gpt-6-sol","status":"partial","record_only":true,"zero_undeclared":false,"family_pins":11,"revert_checks_failed_as_expected":11,"focused_tests_passed":12,"existing_declaration_tests_passed":9,"test_fakery_lint_passed":13,"full_fixtures_run":false}
