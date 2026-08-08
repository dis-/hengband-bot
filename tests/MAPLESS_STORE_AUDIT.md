# Mapless store snapshot audit and fix event

Rule: `store is not None` plus an empty `grids` mapping is absence of a map
observation. It may not select a new grid-memory region, erase a retained cell,
or downgrade a retained fact. The decision receives a copy of the retained last
surface terrain. A store snapshot which does contain grids follows the old merge
path unchanged.

## Reachable reads

| Site | Store-decision reachability and disposition |
| --- | --- |
| `policy.py:2355` `_with_grid_memory` | Single authority. Empty store maps now return retained terrain before region comparison; map-bearing snapshots retain the exact old merge. |
| `policy.py:2420` `_refresh_town_facts` | Reads merged grids and only re-evaluates positions emitted in the raw page. An empty page therefore cannot retract store/building facts. |
| `policy.py:2560-2566` `_choose_key` prologue | Captures raw emitted positions, then replaces the decision snapshot with the memory-bearing snapshot before observation, store routing, shopping, and final invariants. |
| `policy.py:3099` entrance invariant | Store pages return before step-off logic. The following surface page uses emitted terrain plus retained town-visit entrances; no invariant is weakened. |
| `policy.py:2567-2585` accidental-entry guard from `81658c9` | Uses store presence/messages, not map absence. It runs after the merge and retains identical behavior for both emitters. |
| `policy.py:4974` `_observe` and `policy.py:29291` `_build_grid_index` | Both receive the merged snapshot. Empty store pages preserve terrain indexes; transient monster/object/view facts were already stripped when retained and are not invented. |
| `policy.py:11137` atomic withdrawal and `policy.py:11363` atomic deposit | Their entrance `store_number` checks run on the surface entrance decision and therefore use the emitted tile, or retained terrain if the surface emitter is partial. Store completion pages do not lose the retained entrance. |
| `policy.py:14035` supplier reachability | Reads the merged remembered store tiles (or the active static town map); a mapless store page cannot make a supplier disappear. |
| `policy.py:17806` shopping approach owner and `policy.py:17951` travel/entry owner | `grid_at` and visible-goal scans see retained terrain. Entrance ownership, atomic macros, native travel ownership, and failed-entry step-off remain unchanged. |
| `policy.py:29478`, `policy.py:29521`, `policy.py:29561` town entrance/static-map routing | Town facts and remembered terrain remain available. The static map is additive fallback data and does not consume snapshot grids directly. |
| `policy.py:29361`, `policy.py:29776`, `policy.py:30054` walking/exploration | These are structurally reachable from `_decide`, but store dispatch returns before exploration. If called by a store-side owner, they see retained terrain rather than an empty map. |
| `navigation.py` | Contains progress state only; it has no `Snapshot`, `grid_at`, or grid-map read. Distances supplied by shopping/travel owners remain identical. |
| `wilderness_map.py` | Loads static wilderness metadata only and has no snapshot-grid read. Store decisions cannot erode it. |
| `town_maps.py` | Parses immutable town layouts only and has no snapshot-grid read. Policy routing combines it with retained terrain as before. |
| `exploration_ledger.py:146` `note_decision` | The raw latest page is sampled only for persistence; an empty sample is ignored, so a mapless store page cannot replace the fingerprint. Decision-time terrain memory is governed by `_with_grid_memory`. |

## Pins and historical disposition

`ShoppingTest` pins ordinary purchase and leaving-store parity and pins retained
map identity across deliberately different empty-store metadata. The memory pin
fails at `81658c9`: that version resets `_remembered_grids` when the empty store
page's region metadata differs. The purchase and leave decisions themselves are
already equal at `81658c9`; their pins document that the compatibility repair
does not change them.

`HomeOneOperationPerEntryTest` pins a full Home scan burst, atomic-deposit
completion, and atomic-withdrawal completion with every in-store page mapless,
against map-bearing twins. Those decisions are already equal at `81658c9`; the
pins document that their one-send/burst/one-operation contracts remain exact.
No factory was added, duplicated, or removed.

## Verification record

- Focused compatibility pins: 6/6 pass at tip.
- Historical `81658c9`: the memory pin fails because `_remembered_grids` is `{}`
  after the metadata-mismatched empty store page; the five decision-parity pins
  do not claim a historical behavior difference.
- Mutation battery: 5/5 expectations met; `repo_tree_untouched: true`.
- Fakery lint ratchet: 9 existing undeclared violations, 115 declared findings
  in 92 tests; none of the new pins adds a finding.
- Test names: 2,503 discovered at tip; zero deleted test definitions in the diff.
- Full suite run 1: 2,503 tests in 335.076s, pass, one opt-in skip.
- Full suite run 2: 2,503 tests in 327.487s, pass, one opt-in skip.
