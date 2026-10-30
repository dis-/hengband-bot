"""Extract the 2026-10-30 in-store owner-retirement stops (D28).

n1-c life-045 23:45:52: on the General store page (turn 85917) the town
arbiter retired shop-buy (recurrence 2/2) on the decision that composed the
in-store Shovel purchase.  The log-only forgiveness replaced the key with ESC
but kept ``shop:in-store-buy`` as the reason, so the executor refused it as
an in-store buy without prompt gates, the in-store breaker tripped and the
bot stopped (stuck-prompt, then exit:no-marker).  The case keeps that store
board, every store page observed earlier in the ring, the store entrances,
the knowledge rows, the monsters seen and the recorded decision.  Four more
captures with the same breaker row are kept as the recorded population.
"""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_town_stops2 import decisions, rows


ROOT = Path(r"C:\hengband-backups\pdca\captures")
TARGET = Path(__file__).with_name("fixtures") / "owner-retired-in-store-exit-20261030.json.gz"
CASE = ("unfixed-24h-1031/n1-c/life-045", "20261030-234552-stuck-prompt", 85917)
POPULATION = (
    ("n1c-1030-2230/life-038", "20261030-214319-stuck-prompt"),
    ("unfixed-24h-1031/n1-b/life-249", "20261030-023533-stuck-prompt"),
    ("unfixed-24h-1031/n1-b/life-251", "20261030-064805-stuck-prompt"),
    ("unfixed-24h-1031/n1-b/life-256", "20261030-125722-stuck-prompt"),
    CASE[:2],
)


def recorded(capture):
    """The breaker row and the decision whose key it names."""
    tail = decisions(capture / "decision-tail.jsonl")
    breaker = tail[-1]
    decision = next(row for row in reversed(tail)
                    if row.get("decision_sequence") == breaker["in_store_breaker"]["decision_sequence"])
    idle = decision["town_idle_d0"]
    return dict(
        breaker=breaker["in_store_breaker"],
        decision=dict(
            sequence=decision["decision_sequence"], reason=decision["reason"], key=decision["key"],
            operation=decision["in_store"].get("operation"),
            retired=decision["arbiter"]["retirement_set"],
            producer=idle["operation_producer"], trigger=idle["trigger_category"],
            recurrence=(idle["recurrence_count"], idle["recurrence_limit"]),
        ),
    )


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    life, name, turn = CASE
    capture = ROOT / life / "incident-captures" / name
    ring = capture / "snapshots" / "snapshots-current.jsonl.gz"
    observations = rows(ring)
    start = next(i for i, row in enumerate(observations)
                 if row["type"] == "store" and row["turn"] == turn)
    pages = {}
    for row in observations[:start]:
        if row["type"] == "store":
            pages[str(row["store"]["store_type"])] = row["store"]
    grid = next(row for row in reversed(observations[:start]) if "grid_map" in row)
    ids = {m["race_id"] for row in observations[:start + 1]
           for field in ("visible_monsters", "detected_monsters") for m in row.get(field, [])}
    case = dict(
        id=f"{life}/{name}/{turn}",
        sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (ring, capture / "decision-tail.jsonl")},
        board=observations[start],
        pages=pages,
        store_cells=[[c["y"], c["x"], c["s"]] for c in grid["grid_map"]["cells"] if "s" in c],
        knowledge=[row for row in observations[:start] if row["type"] == "knowledge"],
        monraces={str(k): asdict(races[k]) for k in ids if k in races},
        recorded=recorded(capture),
        population={f"{life}/{name}": recorded(ROOT / life / "incident-captures" / name)
                    for life, name in POPULATION},
    )
    with gzip.open(TARGET, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"), default=sorted)
    print(TARGET, TARGET.stat().st_size)
    for key, row in case["population"].items():
        print(key, row["decision"])


if __name__ == "__main__":
    main()
