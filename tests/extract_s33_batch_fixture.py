"""Freeze S3.3 incident seams; never claim these are full policy checkpoints.

Run manually with .s33-plan/captures and incident-rows.jsonl present. Source
paths and line numbers refer to the copied immutable decision tails. A board
is attached only when turn, position and store agree. Other inputs are
explicitly DECLARED CONSTRUCTED in the tests consuming this fixture.
"""
import copy
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extract():
    pins = []
    for source in sorted((ROOT / ".s33-plan/captures").glob("*decisions*.gz")):
        with gzip.open(source, "rt", encoding="utf8") as stream:
            rows = [json.loads(line) for line in stream]
        indices = {len(rows) - 1}
        focus = {"115941": (262, 271), "120434": (223, 226),
                 "170231": (229, 238), "182502": (200, 216),
                 "195851": (310, 328), "202849": (234, 279)}
        focused = set()
        for stamp, (first, last) in focus.items():
            if stamp in source.name:
                focused.update(range(first - 1, min(last, len(rows))))
        indices.update(focused)
        indices.update(i for i, row in enumerate(rows)
                       if (row.get("claim", {}).get("s33_shadow") or {}).get("would_stop"))
        # Keep one onset per family pairing, plus the observed terminal.
        seen = set()
        selected = []
        for i in sorted(indices):
            row = rows[i]
            shadow = row.get("claim", {}).get("s33_shadow") or {}
            pair = (shadow.get("would_stop"), shadow.get("holder_family"))
            if pair in seen and i != len(rows) - 1 and i not in focused:
                continue
            seen.add(pair)
            selected.append(i)
        boards = {}
        state = source.with_name(source.name.replace("bot-decisions", "bot-state-fixed"))
        if state.exists():
            current_map = None
            with gzip.open(state, "rt", encoding="utf8") as stream:
                for line in stream:
                    raw = json.loads(line)
                    if "grid_map" in raw:
                        current_map = raw["grid_map"]
                    if raw.get("type") != "player_turn":
                        continue
                    for i in selected:
                        row = rows[i]
                        if (raw.get("turn") == row.get("turn")
                                and (raw.get("store") or {}).get("store_type") == row.get("store_type")
                                and {"y": raw["player"]["y"], "x": raw["player"]["x"]} == row["position"]):
                            board = copy.deepcopy(raw)
                            if current_map is not None and "grid_map" not in board:
                                board["grid_map"] = copy.deepcopy(current_map)
                            boards[i] = board
        for i in selected:
            pins.append({"source": source.name, "line": i + 1,
                         "row": rows[i], "prior": rows[i - 1] if i else None,
                         "board": boards.get(i)})
    with (ROOT / ".s33-plan/incident-rows.jsonl").open(encoding="utf8") as stream:
        seen = set()
        for line in stream:
            evidence = json.loads(line)
            row = evidence["row"]
            shadow = row.get("claim", {}).get("s33_shadow") or {}
            pair = (Path(evidence["source"]).name, shadow.get("would_stop"),
                    shadow.get("holder_family"), row.get("reason"))
            if pair in seen:
                continue
            seen.add(pair)
            pins.append({"source": Path(evidence["source"]).name,
                         "line": evidence["line"], "row": row,
                         "prior": None, "board": None})
    target = ROOT / "tests/fixtures/s33-batch-seams-20261003.json.gz"
    target.write_bytes(gzip.compress(json.dumps(pins, ensure_ascii=False).encode("utf8"), mtime=0))
    print(f"{len(pins)} seams, {sum(pin['board'] is not None for pin in pins)} boards")


if __name__ == "__main__":
    extract()
