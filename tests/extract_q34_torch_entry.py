"""Extract the intact fresh-warrior boundary from the issue #47 capture."""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge, find_monrace_definitions
from hengbot.quest_knowledge import load_quest_knowledge, find_quest_definitions


def main():
    root = Path(r"C:\hengband-backups\viewing-captures-1029\q34-wait-2100")
    capture = next(root.rglob("20261029-203116-loop-detected"))
    source = capture / "snapshots" / "snapshots-current.jsonl.gz"
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    raw = next(row for row in reversed(rows) if row["type"] == "player_turn"
               and row["player"]["hp"] == row["player"]["max_hp"])
    state = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
    modes = state["modes_and_latches"]
    races_path = find_monrace_definitions(Path.cwd(), None)
    races = load_monrace_knowledge(races_path)
    q34 = load_quest_knowledge(find_quest_definitions(Path.cwd()))[34]
    ids = {race for race, _ in q34.threat_roster}
    ids.update(row["race_id"] for field in ("visible_monsters", "detected_monsters")
               for row in raw.get(field, []))
    decisions = []
    for line in (capture / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            decisions.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    decision = next(row for row in reversed(decisions) if row.get("turn") == raw["turn"])
    case = dict(
        snapshot=raw,
        sources={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (source, capture / "policy-state.json")},
        recorded_readiness=decision["fixedquest_readiness"],
        knowledge=[row for row in rows if row["type"] == "knowledge"],
        monraces={key: asdict(races[key]) for key in ids},
        state={"modes_and_latches": {key: modes[key] for key in
               ("_town_supplier_stock", "_town_supplier_stock_observations")}},
    )
    target = Path(__file__).with_name("fixtures") / "q34-torch-entry-20261029.json.gz"
    with gzip.open(target, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(target, raw["turn"], target.stat().st_size)


if __name__ == "__main__":
    main()
