# S3.3 producer declarations, combined round 4 audit

This remains record only. Producers offer plain-data execution outcomes at their
returns. Claim exit binds the latest matching offer only when both the final
claim owner and final emitted key match. A later `None` offer is ordered with
no-step, done, and identity-bound observation offers. An existing posted wait
with an operation reference survives a later no-key producer probe. The driver
alone records a posted command.

## Sixteen-family source census

| Family | Admitted producer paths and outcome | Known undeclared key/None paths |
| --- | --- | --- |
| equipment-opt | Preparation, refusal, pending session, calibration prerequisite, cache, timeout and search (`policy_equipment.py`; round 3b) | 0 |
| equipment-txn | Session installation, Home/town execution, restoration, sale, inscription and suppressed actions (`policy.py`, `policy_equipment.py`, `policy_shop.py`, `policy_town.py`; round 3b); refused Home withdrawal leave (`policy_home.py:1904`) | 0 |
| calibration | Town key producer's direct outcomes (`policy_calibration.py`; round 3b) | 0 |
| departure | Recall, cancellation, dungeon return, stairs, entrance route and step-off (`policy.py`, `policy_town.py`, `policy_navigation.py`, `policy_supply.py`; round 3b) | 0 |
| fundraising | Floor exit, mining and stockout handoff (`policy_fundraising.py`, `policy.py`; round 3b) | 0 |
| bookkeeping | Skill request, save and dump (`policy.py`; round 3b) | 0 |
| survival / town:kill-mob | Friendly attack, hostile handoff, approach and pursuit (`policy_town.py`; round 3b) | 0 for town:kill-mob |
| identification | Carried, equipped, device and pending-item requests (`policy.py`, `policy_equipment.py`, `policy_town.py`, `policy_identification.py`; round 3b) | 0 |
| curse-enchant | Remove curse and launcher enchant (`policy_town.py`, `policy_equipment.py`; round 3b) | 0 |
| cross-town | Shopping, Morivant identification and town return (`policy_shop.py`, `policy_quest.py`, `policy_town.py`; round 3b) | 0 |
| rumor | Inn read, waits and route refusal (`policy_town.py`; round 3b) | 0 |
| home-visit | Direct page deposit/leave (round 3a); atomic withdraw/deposit and open-page deposit rejected probes now name no-step causes (`policy_home.py:1355`, `policy_home.py:1373`, `policy_home.py:2363`, `policy_home.py:2614`) | 0 known |
| home-errand | Filing now names its next executor or release (`policy_home.py:69`); equipment Home-page filing names its final leave key (`policy_equipment.py:2874`); page leave and unaddressed retry remain from round 3a | 0 known |
| home-scan | Outside/open-page request, page leave, and held observation remain from round 3a; deferred scan names the active bar or holder at its no-key result (`policy.py:5686`, `policy.py:5718`) | 0 known |
| shop-buy / shop-sell | Direct `_shop` page results and one-shot composition remain from round 3a; uncomposable, Home-first plan advance, blocked wait and consumed stop now name final outcomes (`policy_shop.py:4885`, `policy_shop.py:5037`) | 0 known |
| store-router | Entry wait, step-off, short entrance and fallback remain from round 3a; refused relocation, unresolved approach and native travel now name their key or no-step (`policy_shop.py:4616`, `policy_shop.py:4717`, `policy_town.py:4172`) | 0 known |

The original round 3a partials were resolved by offering the producer's result
at its own return. A rejected Home composer probe can be followed by a key from
another producer; the final owner/key check discards the probe. Home filing is
a Boolean helper, so its `None` request offer and the equipment caller's leave
offer have separate identities. A deferred Home scan offer names its holder but
cannot replace a posted, identity-bound observation wait. The direct shop page
wrapper already declares purchases, sales, leaves and no-step outcomes; the
one-shot composer now declares the remaining uncomposable and plan-advance
returns. An unresolved shopping direction retains its legacy emitted string
`"None"`; its declaration matches that actual key.

There are **zero known undeclared admitted key/None paths in these sixteen
family scopes** after this source audit. The survival row covers the named town
monster producer only; other survival producers were outside this declaration
round. Boolean and void helpers do not emit a key. This is not a full replay or
gate measurement, and no claim is made about unseen runtime branches outside
the inspected producer scopes.

## Verification

`tests.test_execution_declaration`: 20 passed;
`tests.test_declarations_r3b`: 13 passed;
`tests.test_declarations_r4`: 8 passed;
`tests.test_test_fakery_lint`: 13 passed. Each of the eight new class pins failed
under one targeted source-removal check, and the source was restored after each
check. No prohibited runner, gate, full suite, town producer purity sweep or
long recorded replay was run. Claude owns the suite, gates and mismatch counts.

Merge commit: `924358ed`. The round 4 implementation and this audit are committed
together.
