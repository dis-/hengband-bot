"""Extract the 2026-10-30 n1-c Magic-Eater town stops (D9 and the Lv7 Q1 stop).

Lives 021, 022 and 024 retired after Q1 on town:blocked:owner-retired-burst;
life 023 stopped before Q1 on quest:blocked:opening-route (no-key-exhausted).
Each case keeps the boundary board the test starts from, the latest observed
page of every store in the same snapshot ring, the store entrances, the
knowledge rows before the board and the recorded supplier census and
fundraising target.
"""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path(r"C:\hengband-backups\viewing-captures-1030\n1c-lives-21-24")
TARGET = Path(__file__).with_name("fixtures") / "me-town-stops-20261030.json.gz"
# (life, capture, boundary row): D9 starts on the last observed kit-supplier
# page; the Lv7 stop starts on its final outside board.
CASES = (
    ("life-021", "20261030-142920-town-blocked-owner-retired-burst", "last-store"),
    ("life-022", "20261030-143543-town-blocked-owner-retired-burst", "last-store"),
    ("life-024", "20261030-144221-town-blocked-owner-retired-burst", "last-store"),
    ("life-023", "20261030-143732-no-key-exhausted", "last-turn"),
)
STATE_KEYS = ("_town_supplier_stock", "_town_supplier_stock_observations", "_fundraising_mode")


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def decisions(path):
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            found.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    return found


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    cases = []
    for life, name, which in CASES:
        capture = ROOT / life / "incident-captures" / name
        ring = capture / "snapshots" / "snapshots-current.jsonl.gz"
        observations = rows(ring)
        tail = decisions(capture / "decision-tail.jsonl")
        state_path = capture / "policy-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        kind = "store" if which == "last-store" else "player_turn"
        start = max(i for i, row in enumerate(observations) if row["type"] == kind)
        pages = {}
        for row in observations:
            if row["type"] == "store":
                pages[row["store"]["store_type"]] = row["store"]
        board = observations[start]
        cells = [[c["y"], c["x"], c["s"]] for c in observations[-1]["grid_map"]["cells"] if "s" in c]
        ids = {m["race_id"] for row in observations
               for field in ("visible_monsters", "detected_monsters") for m in row.get(field, [])}
        modes = state["modes_and_latches"]
        last = tail[-1]
        cases.append(dict(
            id=f"{life}/{name}",
            sources={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (ring, capture / "decision-tail.jsonl", state_path)},
            board=board,
            pages={str(k): v for k, v in pages.items()},
            store_cells=cells,
            knowledge=[row for row in observations[:start] if row["type"] == "knowledge"],
            monraces={str(k): asdict(races[k]) for k in ids if k in races},
            state={key: modes[key] for key in STATE_KEYS},
            supply_stockout_gold_target=state["state"].get("_supply_stockout_gold_target"),
            recorded=dict(
                kind=json.loads((capture / "meta.json").read_text(encoding="utf-8"))["kind"],
                reason=last.get("reason"), key=last.get("key"), gold=last["player"]["gold"],
                fixedquest_readiness=last.get("fixedquest_readiness"),
                shop_selector=last.get("shop_selector"),
            ),
        ))
    with gzip.open(TARGET, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"), default=sorted)
    print(TARGET, TARGET.stat().st_size)
    for case in cases:
        print(case["id"], case["board"]["turn"], case["recorded"]["kind"], case["recorded"]["reason"])


if __name__ == "__main__":
    main()
