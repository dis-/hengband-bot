"""Freeze the #47 drained-strength inputs (n1-c life-096, 2026-11-01).

Sources (read-only gzip copies of the viewing server's
``~/hengbot-soak/n1-c/life-096/state.jsonl`` and ``jsonlog/bot-decisions.jsonl``,
taken 17:35 into ``<copies>/{state,bot-decisions}.jsonl.gz``, and the death
capture ``<copies>/rest/incident-captures/20261101-173135-player-death/policy-state.json``).

Two cases, each starting on a recorded Alchemist page where STR is drained
(``player.stats.str.drained``) and 腕力復活の薬 is on the shelf and affordable:
- ``prepare``: zero-based state line 116 (turn 1462282, after the recorded
  'pj1\\r\\r' recall purchase; recorded next decision 92 '\\x1b' shop:in-store-done),
  knowledge rows 78 (``~f``) and 95 (Home list), entrances from line 114.
- ``mine``: line 649 (turn 1645367; recorded decision 610 '\\x1b'
  shop:observe-and-leave, "observed-page-nothing-wanted"), knowledge rows 639
  (``~f``) and 95, entrances from line 648.
The recorded decision rows of both pages are kept (reason, key, fundraising,
shop_selector), and the Magic-Eater staff record of the death capture.

Only this tool reads the copies; the committed test reads the frozen file.
Usage: python tests/extract_me_stat_restore_fixture.py <copies>
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "me-stat-restore-20261101.json.gz"
# case: (store page line, outside board line with the entrances, knowledge lines, turn)
CASES = {"prepare": (116, 114, (78, 95), 1462282),
         "mine": (649, 648, (639, 95), 1645367)}
DEATH = "rest/incident-captures/20261101-173135-player-death/policy-state.json"


def main(copies: Path) -> None:
    with gzip.open(copies / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        lines = [json.loads(line) for line in stream]
    recorded = {}
    with gzip.open(copies / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("store_type") == 4 and row.get("turn") in {t for *_, t in CASES.values()}:
                recorded.setdefault(row["turn"], []).append({
                    name: row.get(name) for name in (
                        "decision_sequence", "turn", "reason", "key", "fundraising",
                        "shop_selector")})
    races = load_monrace_knowledge(find_monrace_definitions(ROOT, None))
    state = json.loads((copies / DEATH).read_text(encoding="utf-8"))
    cases = {}
    for name, (page, outside, knowledge, turn) in CASES.items():
        board, entrance = lines[page], lines[outside]
        assert (board["type"], board["turn"], board["store"]["store_type"]) == ("store", turn, 4)
        assert board["player"]["stats"]["str"]["drained"]
        ids = {m["race_id"] for field in ("visible_monsters", "detected_monsters")
               for m in entrance.get(field, [])}
        cases[name] = dict(
            board=board,
            pages={"4": board["store"]},
            store_cells=[[c["y"], c["x"], c["s"]] for c in entrance["grid_map"]["cells"] if "s" in c],
            knowledge=[lines[index] for index in knowledge],
            monraces={str(k): asdict(races[k]) for k in ids if k in races},
            recorded=recorded[turn],
        )
    document = dict(cases=cases, me_staff_sequence=state["state"]["_me_staff_sequence"])
    OUT.write_bytes(gzip.compress(json.dumps(
        document, ensure_ascii=False, sort_keys=True, default=sorted).encode("utf-8"), mtime=0))
    print(OUT.name, OUT.stat().st_size, hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main(Path(sys.argv[1]))
