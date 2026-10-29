"""Extract all eight incident boundaries for issue #47 (2026-10-29)."""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import _parse_items
from hengbot.monrace_knowledge import load_monrace_knowledge, find_monrace_definitions
from hengbot.quest_knowledge import load_quest_knowledge, find_quest_definitions

ROOT = Path(r"C:\hengband-backups\viewing-captures-1029\lv7-stop")
TARGET = Path(__file__).with_name("fixtures") / "lv7-town-stop-20261029.json.gz"


def rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    captures = []
    race_path = find_monrace_definitions(Path.cwd(), None)
    races = load_monrace_knowledge(race_path)
    q34 = load_quest_knowledge(find_quest_definitions(Path.cwd()))[34]
    for path in sorted(ROOT.rglob("decision-tail.jsonl")):
        decisions = rows(path)
        snapshots = path.parent / "snapshots" / "snapshots-current.jsonl.gz"
        observations = rows(snapshots)
        state_path = path.parent / "policy-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        keep = ("turn", "decision_sequence", "reason", "key", "position", "claim",
                "arbiter", "town_plan", "departure_block", "fixedquest_readiness",
                "fundraising", "equipment_optimization", "town_idle_d0")
        window = []
        for decision in decisions:
            record = {k: decision[k] for k in keep if k in decision}
            record["offered_work_ids"] = [(entry.get("work") or {}).get("work_id")
                                          for entry in decision.get("town_work", [])
                                          if entry.get("seam") == "offer"]
            window.append(record)
        parts = path.relative_to(ROOT).parts
        snapshot = next(row for row in reversed(observations) if row["type"] == "player_turn")
        action = decisions[-1]["equipment_optimization"].get("transaction_next")
        transaction_item = None
        if action:
            identity = action["item_id"].split(":")[1]
            transaction_item = next(
                raw for row in observations for raw in row.get("inventory", [])
                if equipment_identity(_parse_items([raw], protocol=3)[0]) == identity
            )
        pages = {}
        for row in observations:
            if row.get("store"):
                pages[row["store"]["store_type"]] = row
        race_ids = {row["race_id"] for field in ("visible_monsters", "detected_monsters")
                    for row in snapshot.get(field, [])}
        # The lowered Magic-Eater gate now evaluates Q34's entire roster.
        race_ids.update(race for race, _ in q34.threat_roster)
        captures.append(dict(
            id="/".join((parts[0], parts[1], path.parent.name)),
            sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (path, snapshots, state_path)},
            monrace_source_sha256=hashlib.sha256(race_path.read_bytes()).hexdigest(),
            snapshot=snapshot,
            pages=pages,
            monraces={key: asdict(races[key]) for key in race_ids},
            transaction_item=transaction_item,
            knowledge=[row for row in observations if row["type"] == "knowledge"],
            decisions=window,
            state=state,
        ))
    with gzip.open(TARGET, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(captures, stream, ensure_ascii=False, separators=(",", ":"), default=sorted)
    print(TARGET, len(captures), TARGET.stat().st_size)
    for case in captures:
        print(case["id"], case["snapshot"]["turn"],
              [(k.get("knowledge", {}).get("category")) for k in case["knowledge"]])


if __name__ == "__main__":
    main()
