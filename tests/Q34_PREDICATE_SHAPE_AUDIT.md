# Q34 offer predicate snapshot-shape audit

`python scripts/owner_map.py` on the fix tree reports:

```
reasons: 592
facts: 1135
starvation-prone: 66
```

The generator maps stored ownership facts; an AST/`rg` enumeration of the two
method facts found the following consumers.  Stabilising
`_fixed_quest_is_offered` preserves or fixes each one as follows:

| Consumer | Effect of the stable Q34 offer |
| --- | --- |
| `_opening_q34_active` | The opening ownership contract no longer changes merely because the player opens a store page. |
| `_choose_key` | Home-knowledge acquisition remains suppressed while the Q34 opening owns town. |
| `_decide` (blocked/owned equipment guards) | The two ordinary equipment owners remain suppressed on both sides of a store boundary. |
| `_opening_q34_town_key` | Q34 keeps sole non-emergency town ownership in a store and after leaving it. |
| `_opening_q34_torch_shortage` | The mandatory torch reservation does not disappear on a mapless store page. |
| `_recall_shortage_opening_exempt` | The opening exemption remains consistent while shopping. |
| `_town_need_candidates` (opening and fundraising branches) | The opening need keeps precedence and fundraising needs remain suppressed in stores. |
| `_next_required_store_type` | A mapless Home page cannot revive fundraising and select Home as a new approach target. |
| `_start_fundraising` | Opening Q34 continues to reject fundraising inside stores. |
| `_home_rearm_key` (weaponless and restoration branches) | Q34's sanctioned rearm paths remain available without releasing general Home ownership. |
| `_fixed_quest_target` | An untaken offered Q34 remains a candidate on either snapshot shape. |
| `_fixed_quest_head` (Q34 precedence and generic offer branch) | Q34-first precedence and conditional-offer selection see the same offer fact. |
| `_evaluate_fixed_quest_readiness` | The opening-only readiness exception remains stable during store decisions. |

The same-shape audit enumerated every function in `policy.py` that reads
`snapshot.grids` and reviewed the town gates among them.  No second ownership
predicate has the same defect.  The other town readers are
`_town_need_supplier_reachable`, `_shopping_approach_step`, `_town_teleport_key`,
`_fixed_quest_building_positions`, `_fixed_quest_entrance_positions`,
`_effective_town_id`, and `_town_map_active`.  Supplier, approach, teleport,
and fixed-quest position readers already have remembered/static town-map
fallbacks; effective-town and active-map selection use exported town/dimension
metadata.  Moreover, public decisions pass through `_with_grid_memory` before
these routing readers.  Therefore none loses its town ownership truth solely
because the store emitter omits `nearby_grids`; no additional predicate is
changed in this patch.
