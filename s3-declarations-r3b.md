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
| equipment-txn | `policy.py` session installation, Home catalogue approach, heavy-curse inscription and light wield; `policy_equipment.py` Home/town executor, town owner, weapon restoration and prepared action; `policy_town.py` random-teleport suppression and dominated-item destroy; `policy_shop.py` dominated-item sale and store exit | **Yes for admitted key/None exits**. The accepted pending-action wait keeps its exact command ID and does not post the pending action again. |
| calibration | `policy_calibration.py` `_calibration_town_key`: all direct key/`None` returns, including deposit and restore handoffs, aborts, scan, strip, capture and travel | **Yes for the direct key producer**. The other decorated calibration helpers return booleans rather than keys. The Home executor's own operation outcomes remain in its separate family audit. |
| departure | `policy_town.py` recall selection/read, cancellation, confirmation, dungeon return, repetition descent and entrance step-off; `policy.py` town recall wait/leave and descent route/blocker; `policy_navigation.py` stair posting and timeout probe; `policy_supply.py` no-safe-route wait | **Yes for admitted key/None exits**. Stair suppressor pass-through preserves the originating producer's declaration. |
| fundraising | `policy_fundraising.py` run, floor exit, mining tunnel/closure/tapped-out paths; `policy.py` Identify staff stockout mining handoff | **Yes for admitted key/None exits**. Delegated floor-exit and mining-finish keys bind the child producer's exact key. |
| bookkeeping | `policy.py` skill-exp request, periodic save and character dump | **Yes for selected bookkeeping work**. Save/dump pass-through returns preserve the prior producer's key and owner. |
| survival / town:kill-mob | `policy_town.py` `_town_kill_mob_key`: friendly attack, approach, last-known pursuit and all no-step exits | **Yes for town:kill-mob**. This row does not claim the other survival producers. |
| identification | `policy.py` `_verified_destroy_key`; `policy_equipment.py` town equipped identification; `policy_town.py` town device and pending item processing; `policy_identification.py` carried and dungeon equipment identification | **Yes for admitted key/None exits**. Home source filing is a Boolean request into the Home executor, not an emitted identification key. |
| curse-enchant | `policy_town.py` `_town_remove_curse_key`; `policy_equipment.py` `_town_enchant_launcher_key` | **Yes for both direct producers**. |
| cross-town | `policy_shop.py` `_cross_town_shopping_key`; `policy_quest.py` `_morivant_full_identify_key`; `policy_town.py` walk-in return after fundraising | **Yes for admitted key/None exits**. Morivant Home phases declare an acting handoff; observed completion declares done. The store-router teleport executor is a different family. |
| rumor | `policy_town.py` rumor block in `_town_special_key`: supply/fund waits, approach, batch, and unavailable route/step | **Yes for the rumor block**. |

The assigned producer return census has **zero known undeclared key/`None`
paths**. There is no path that could not be declared under the record-only
contract. This is a source audit, not a full replay coverage claim. Boolean
helpers and a pass-through return that preserves another producer's final key
do not create a new claim-owner offer. A generic claim-exit declaration was not
added.

## Verification and limits

`tests.test_declarations_r3b`: 13 passed. Each of the eleven family class pins
failed when its selected declaration write was suppressed once. Existing
`tests.test_execution_declaration`: 9 passed. `tests.test_test_fakery_lint`: 13
passed after replacing five collaborator-heavy pins with real fixtures or
narrow branch setup. `tests.test_policy_fundraising`: 50 passed. The forbidden
replay runners, gate scripts, full suite and town producer purity modules were
not run. The key-composition branches still return their existing key, with
both switches OFF and with S3.3 ON; the new declarations are record-only.
OFF replay identity and S3.3 ON replay equivalence were not measured because
the prompt forbade those runs.

Commits: `3aa2911a`, `2f102335`, `39fbbcd0`, `a44e4f57`, `64f9e2e3`,
`38984062`, `0b50fe40`, `7b70e896`, `20a58b14`, `d0656612`, `745b73d7`,
`ca709671`, `44b8e402`, `95f2eb25`, `908ce3a3`, `ff3e30bc`, `2239c075`,
`cc983233`, `9a3baa64`, `a9be3382`, `08a3e66a`,
`09e2e7b8`, `f29f0ea0`, `667f0435`, `cece4d10`, `37ce6760`,
`e698dfcc`, `11693246`, `3d34747f`.

{"topic":"declarations-r3b","implementer":"gpt-6-sol","status":"source-audit-complete","record_only":true,"zero_known_undeclared":true,"family_pins":11,"revert_checks_failed_as_expected":11,"focused_tests_passed":13,"existing_declaration_tests_passed":9,"fundraising_tests_passed":50,"test_fakery_lint_passed":13,"full_fixtures_run":false}
