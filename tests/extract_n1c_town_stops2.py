"""Extract the 2026-10-30 20:34-21:20 n1-c Magic-Eater town stops (D25).

Each case starts on the recorded Magic-shop page where the bot spent its
fundraising gold on a wand or staff as "food" (the first in-store buy of
that visit).  It keeps that board, the latest page of every store observed
up to it, the store entrances, the knowledge rows before it, the decision's
fundraising mode and what the recorded visit bought.
"""
import hashlib
import json
import zlib
import gzip
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path(r"C:\hengband-backups\pdca\captures\n1c-1030-2100")
TARGET = Path(__file__).with_name("fixtures") / "n1c-town-stops2-20261030.json.gz"
# (life, capture, turn of the Magic-shop page whose first buy is the case)
CASES = (
    ("life-033", "20261030-203433-no-key-exhausted", 167147),
    ("life-036", "20261030-205554-no-key-exhausted", 366504),
)
STATE_KEYS = ("_town_supplier_stock", "_town_supplier_stock_observations")


def rows(path):
    """Concatenated, possibly partially written gzip members."""
    data, text = path.read_bytes(), b""
    data = data[max(0, data.find(b"\x1f\x8b\x08")):]  # a tail-capped ring
    while data:
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            text += stream.decompress(data)
        except zlib.error:
            break
        if not stream.eof:
            break
        data = stream.unused_data
    found = []
    for line in text.decode("utf-8", "replace").splitlines():
        try:
            found.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The live generation may end in a partial line.
    return found


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
    for life, name, turn in CASES:
        capture = ROOT / life / "incident-captures" / name
        ring = capture / "snapshots" / "snapshots-current.jsonl.gz"
        observations = rows(ring)
        tail = decisions(capture / "decision-tail.jsonl")
        state_path = capture / "policy-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        start = min(i for i, row in enumerate(observations)
                    if row["type"] == "store" and row["turn"] == turn)
        pages = {}
        for row in observations[:start + 1]:
            if row["type"] == "store":
                pages[row["store"]["store_type"]] = row["store"]
        board = observations[start]
        grid = next(row for row in reversed(observations[:start]) if "grid_map" in row)
        cells = [[c["y"], c["x"], c["s"]] for c in grid["grid_map"]["cells"] if "s" in c]
        ids = {m["race_id"] for row in observations[:start + 1]
               for field in ("visible_monsters", "detected_monsters") for m in row.get(field, [])}
        visit = [row for row in tail if row["turn"] == turn]
        modes = state["modes_and_latches"]
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
            fundraising_mode=visit[0]["fundraising"]["mode"],
            recorded=dict(
                kind=json.loads((capture / "meta.json").read_text(encoding="utf-8"))["kind"],
                reason=tail[-1]["reason"],
                visit=[(row["reason"], row["key"], row["player"]["gold"],
                        (row.get("shop_selector") or {}).get("wanted_purchase"),
                        row.get("procurement_requirements"))
                       for row in visit],
            ),
        ))
    with gzip.open(TARGET, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, separators=(",", ":"), default=sorted)
    print(TARGET, TARGET.stat().st_size)
    for case in cases:
        print(case["id"], case["board"]["turn"], case["fundraising_mode"],
              [row[:3] for row in case["recorded"]["visit"]])


if __name__ == "__main__":
    main()
