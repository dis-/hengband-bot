"""Extract tests/fixtures/aimed-item-direction-1123.json.gz (owner answer (b)-5, 2026-11-23).

Run on the soak host (python3 only, no hengbot import), from ``~/hengbot-soak``::

    python3 - n1-a/life-535 n1-a/life-535 n1-b/life-416 n1-c/life-221 < extract_....py > out.json

The first argument is the life whose decision log gives the game-turn advance of each posted
key kind (bot-decisions.jsonl[.1], 2026-11-23 12:41-13:02 JST, after 57a80bc0a was deployed);
the others (the first included) are the lives whose jsonlog/input-context-shadow.jsonl holds the
``composed-passthrough`` rows the (a)-3 recording logged.  Output: the passthrough rows (owner,
command, key, suffix; the first of each (owner, key) with its count) and, per key kind, a
Counter of the turn advance to the next decision (consecutive decision sequences only), with
the first five concrete pairs of each kind.
"""

import collections
import json
import sys
from pathlib import Path

DECISION_FILES = ("bot-decisions.jsonl.1", "bot-decisions.jsonl")
WINDOW = "2026-11-23T1"           # 2026-11-23 10:00-19:59 JST rows only


def kind_of(key):
    if key.startswith("f") and key[2:4] == "*t":
        return "fire-target"         # 'f' + ammo + '*t5\x1b'
    if key.startswith("f") and key[2:4] == "*p":
        return "fire-offset"         # 'f' + ammo + '*p<moves>t5\x1b'
    if key[:1] == "f" and len(key) == 3 and key[2] in "12346789":
        return "fire-direction"
    if key[:1] == "a" and len(key) == 3 and key[2] in "12346789":
        return "wand-direction"
    if key in tuple("12346789"):
        return "step"
    return None


def deltas(life):
    rows = []
    for name in DECISION_FILES:
        path = Path(life) / "jsonlog" / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.startswith('{"time": "' + WINDOW):
                    continue
                row = json.loads(line)
                if "turn" in row and "key" in row and "decision_sequence" in row:
                    rows.append((row["decision_sequence"], row["turn"], row["key"], row["reason"],
                                 row["time"]))
    counts = collections.defaultdict(collections.Counter)
    pairs = collections.defaultdict(list)
    for (seq, turn, key, reason, time), (seq2, turn2, key2, _reason2, _time2) in zip(rows, rows[1:]):
        kind = kind_of(key)
        if kind is None or seq2 != seq + 1:
            continue
        counts[kind][turn2 - turn] += 1
        if len(pairs[kind]) < 5:
            pairs[kind].append({"time": time, "sequence": seq, "turn": turn, "key": key,
                                "reason": reason, "next_turn": turn2, "next_key": key2})
    return ({kind: {str(k): v for k, v in sorted(c.items())} for kind, c in sorted(counts.items())},
            dict(sorted(pairs.items())), (rows[0][4], rows[-1][4]) if rows else None)


def passthroughs(lives):
    first, counts = {}, collections.Counter()
    for life in lives:
        path = Path(life) / "jsonlog" / "input-context-shadow.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if '"composed-passthrough"' not in line:
                    continue
                row = json.loads(line)
                site = (life, row.get("owner"), row.get("key"))
                counts[site] += 1
                first.setdefault(site, {"life": life, "time": row.get("time"),
                                        "owner": row.get("owner"), "command": row.get("command"),
                                        "key": row.get("key"), "suffix": row.get("suffix"),
                                        "expected": row.get("expected")})
    return [dict(first[site], count=counts[site]) for site in sorted(first, key=str)]


def main():
    life, *lives = sys.argv[1:]
    turn_advance, pairs, window = deltas(life)
    json.dump({"source": {"decisions": life, "window": window,
                          "passthrough_lives": sorted(set(lives))},
               "turn_advance": turn_advance, "pairs": pairs,
               "passthrough": passthroughs(sorted(set(lives)))},
              sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
