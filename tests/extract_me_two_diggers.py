"""Extract the 2026-10-30 n1-c life-036 mining-kit board (one digger).

The Magic-Eater bought one Shovel on the General store page (gold 621 ->
525, ten more Shovels on the shelf), spent the rest on 20 Treasure Detection
scrolls and mined its first explicit-target run with one digger.  The case
keeps that General store page (the board after the first Shovel), every
store page observed earlier in the same snapshot ring, the store entrances,
the knowledge rows before the board and the monsters seen.
"""
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path(r"C:\hengband-backups\pdca\captures\n1c-1030-2100")
TARGET = Path(__file__).with_name("fixtures") / "me-two-diggers-20261030.json.gz"
LIFE, CAPTURE, TURN = "life-036", "20261030-205554-no-key-exhausted", 81777


def rows(path):
    found = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        try:
            for line in stream:
                if line.strip():
                    found.append(json.loads(line))
        except (EOFError, OSError):
            pass  # The ring's last generation may end mid-member.
    return found


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ring = ROOT / LIFE / "incident-captures" / CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
    observations = rows(ring)
    # The General store page after the kit's first Shovel (inventory has it).
    start = next(i for i, row in enumerate(observations)
                 if row["type"] == "store" and row["turn"] == TURN
                 and row["store"]["store_type"] == 0
                 and any(it.get("tval") == 20 for it in row["inventory"]))
    pages = {}
    for row in observations[:start]:
        if row["type"] == "store":
            page = row["store"]
            pages.setdefault(str(page["store_type"]), {})[str(page["page_top"])] = page
    board = observations[start]
    outside = next(row for row in reversed(observations[:start]) if row["type"] == "player_turn")
    cells = [[c["y"], c["x"], c["s"]] for c in outside["grid_map"]["cells"] if "s" in c]
    ids = {m["race_id"] for row in observations[:start + 1]
           for field in ("visible_monsters", "detected_monsters") for m in row.get(field, [])}
    case = dict(
        id=f"{LIFE}/{CAPTURE}/{TURN}",
        sources={str(ring.relative_to(ROOT)): hashlib.sha256(ring.read_bytes()).hexdigest()},
        board=board,
        pages=pages,
        store_cells=cells,
        knowledge=[row for row in observations[:start] if row["type"] == "knowledge"],
        monraces={str(k): asdict(races[k]) for k in ids if k in races},
        # The recorded continuation: Alchemist 525 -> 69 (19 scrolls), Black
        # market 69 -> 6 (one more), the first mining run with one Shovel.
        recorded=dict(
            next_purchases=[
                (row["turn"], row["store"]["store_type"], row["player"]["gold"])
                for row in observations[start + 1:]
                if row["type"] == "store" and row["turn"] <= 82303
            ],
            departure=next(
                dict(turn=row["turn"], gold=row["player"]["gold"],
                     diggers=[it["name"] for it in row["inventory"] + row["equipment"]
                              if it.get("tval") == 20])
                for row in observations[start:]
                if row["type"] == "player_turn" and row["floor"]["dungeon_id"] == 2
            ),
        ),
    )
    with gzip.open(TARGET, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump([case], stream, ensure_ascii=False, separators=(",", ":"), default=sorted)
    print(TARGET, TARGET.stat().st_size, case["board"]["turn"], case["recorded"]["departure"])


if __name__ == "__main__":
    main()
