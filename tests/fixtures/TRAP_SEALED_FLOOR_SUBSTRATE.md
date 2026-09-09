# Trap-sealed floor substrate

`trap-sealed-floor-dungeon4-level16.jsonl.gz` is the deterministic extraction
of all snapshots where `floor.dungeon_id == 4` and `floor.level == 16` from
`jsonlog/bot-state-fixed.jsonl` at task base `e020324`. It contains 1,888 raw
JSONL rows in source order.

- Source SHA-256: `280505d9c977acb079ea0ec69b73aa09a4988efa7e4ee9a6c0d719610b02fc17`
- Uncompressed selected-row SHA-256: `342df9bb895f79b372762d2b54b3ccc90e7d8ea9d0fef8776173e50c371bdd9e`
- Deterministic gzip SHA-256: `12bf22ba6d6a0de88dc9712c660741a8949e48481fb5a7cd44e76b1b2c6880de`

The extraction parses every source row, selects the two exact integer floor
fields above, normalizes each selected row to one trailing LF, joins them in
source order, and writes gzip level 9 with an empty filename and `mtime=0`.
The regression test then feeds every row through `parse_snapshot` and
`policy.prime` on one instance; `prime` is the public observer that calls the
real `_build_grid_index` producer.
