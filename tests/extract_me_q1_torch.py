"""Extract the Lv7 Magic-Eater town boundary that stopped before quest 1 (D17)."""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge, find_monrace_definitions
from hengbot.quest_knowledge import load_quest_knowledge, find_quest_definitions


ROOT = Path(r"C:\hengband-backups\magic-eater-captures-1029\town-nokey-2308\incident-captures")


def boundary(name):
    capture = ROOT / name
    source = capture / "snapshots" / "snapshots-current.jsonl.gz"
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    raw = next(row for row in reversed(rows) if row["type"] == "player_turn")
    state = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
    modes = state["modes_and_latches"]
    decisions = []
    for line in (capture / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            decisions.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    decision = next(row for row in reversed(decisions) if row.get("turn") == raw["turn"])
    return capture, source, rows, raw, modes, decision


def main():
    # 23:07:47: the reward pickup completed and the route latched a stop.
    # 23:08:06: after a restart the shop census refused the potion stock
    # demanded by the class-16 force gate.
    _, _, _, reward_raw, _, reward_decision = boundary("20261029-230747-no-key-exhausted")
    capture, source, rows, raw, modes, decision = boundary("20261029-230806-no-key-exhausted")
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    q1 = load_quest_knowledge(find_quest_definitions(Path.cwd()))[1]
    ids = {race for race, _ in q1.threat_roster}
    for board in (raw, reward_raw):
        ids.update(row["race_id"] for field in ("visible_monsters", "detected_monsters")
                   for row in board.get(field, []))
    visit = [row for row in rows if row["type"] == "store" and row["turn"] in (82212, 82434)]
    general = next(row for row in rows if row["type"] == "store" and row["store"]["store_type"] == 0)
    case = dict(
        snapshot=raw,
        reward_snapshot=reward_raw,
        sources={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (source, capture / "policy-state.json")},
        recorded_readiness=decision["fixedquest_readiness"],
        recorded_key=decision["key"], recorded_reason=decision["reason"],
        recorded_reward_failure=reward_decision["fixedquest_readiness"]["opening_route_failure"],
        store_visit=visit,
        # The Outpost general store page of the same capture (turn 75108).
        general_page=general["store"],
        knowledge=[row for row in rows if row["type"] == "knowledge"],
        monraces={key: asdict(races[key]) for key in ids},
        state={"modes_and_latches": {key: modes[key] for key in
               ("_town_supplier_stock", "_town_supplier_stock_observations")}},
    )
    target = Path(__file__).with_name("fixtures") / "me-q1-torch-20261029.json.gz"
    with gzip.open(target, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(target, raw["turn"], target.stat().st_size)


if __name__ == "__main__":
    main()
