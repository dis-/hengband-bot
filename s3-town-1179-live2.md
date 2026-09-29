# Town sequence 1177: observed deposit, frozen continuation needs a ruling

Fixture: `tests/fixtures/town-approach-retired-20260925.jsonl.gz` (SHA-256
`249feeff221d652c51bb8b56d9c4ec021ce17bd309f39b17d9d53f940e106093`).
The list index and decision sequence differ. These are the actual recorded
boards at indices 1178–1182, including their inventory, Home stock metadata,
and game messages.

| List index / sequence | Recorded key / reason | Relevant board evidence |
| --- | --- | --- |
| 1178 / 1176 | `dm\r` / `equipment-transaction:deposit` | Before the command, pack `m` is `★更正せるセオデン王のビークド・アックス (2d6) (+8,+10) (+3) {+賢耐;遅祝/竜~感}`; pack `l` is `耐冷の革製スモール・シールド [3,+2] {r冷, .}`. Home (`store_type=7`) has `stock_num=130`. |
| 1179 / 1177 | ESC / `home-errand:filed:combat-weapon` | Home has `stock_num=131`; the axe is absent from the pack, and arrows have moved to `m`. The first board says the axe was put down `(m)` and is no longer carried. The shield remains in pack `l`. The Home page is `page_top=104`, so this page does not display the newly stored axe. |
| 1180 / 1178 | `5` / `equipment-transaction:atomic-deposit` | Outside Home, the axe remains absent; shield remains at `l`. |
| 1181 / 1179 | `dl` then ESC / `home:atomic-deposit` | Before this later command, the shield is still pack `l`. This is a separate Home deposit reason, rather than an equipment transaction step. |
| 1182 / 1180 | `5` / `equipment-transaction:travel-home:await-entry` | The shield is gone from the pack; the game says it was put down `(l)` and is no longer carried. Home `stock_num` rises to 132. The next recorded transaction result at index 1183 / sequence 1181 is `equipment-transaction:withdraw-missing`, consistent with the transaction proceeding toward a withdrawal, not a shield deposit. |

**Answer (a): yes.** By the board for sequence 1177, the posted `dm` axe
deposit has visibly taken effect. Pack `l` is the cold-resistant small leather
shield. Depositing `l` is the later `home:atomic-deposit` command, not the
transaction session's next planned action. The fixture does not expose the
session plan itself; the separate reason and later transaction withdrawal are
the recorded evidence for that distinction.

**Decision (b): stop for Claude's decision.** The frozen expected `\r` /
`equipment-transaction:atomic-deposit` at list index 1179 would wait after
the deposit effect is already observed. It encodes the live continuation-wait
bug rather than a valid continuation for this board. The expectation table and
policy are untouched. The local `test_crossarea_live2.py` unobserved-action pin
uses a board before the command's effect, so it does not exercise this path.
