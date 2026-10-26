"""Extract Issue #47 round-2 prompt evidence; never connects to a game."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


SOURCE = Path("C:/hengband-backups/state-logs/q34-fresh-chest-prompt-1026/captures")
TARGET = Path(__file__).with_name("fixtures") / "q34-chest-prompt-20261026.json.gz"


def extract():
    captures = []
    for directory in sorted(SOURCE.iterdir()):
        def read(name):
            return gzip.decompress((directory / name).read_bytes()).decode("utf-8")

        control = json.loads(read("control-at-stop.json.gz"))
        rows = [json.loads(line) for line in read("state.jsonl.gz").splitlines()]
        decisions = [json.loads(line) for line in read("bot-decisions.jsonl.gz").splitlines()]
        posts = [json.loads(line) for line in read("bot-posted-characters.jsonl.gz").splitlines()]
        turns = [(index + 1, row) for index, row in enumerate(rows)
                 if row["type"] == "player_turn"][-9:]
        skill = next(row for row in reversed(rows)
                     if row["type"] == "knowledge" and row["knowledge"]["category"] == "skill_exp")
        captures.append({
            "capture": directory.name,
            "sha256": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                       for name in ("control-at-stop.json.gz", "state.jsonl.gz",
                                    "bot-decisions.jsonl.gz", "bot-posted-characters.jsonl.gz")},
            "screen": control["screen"],
            "stop_state": control["state"],
            "skill": skill,
            "source_lines": [index for index, _ in turns],
            "rows": [row for _, row in turns],
            "decisions": [{key: row[key] for key in ("turn", "reason", "key")}
                          for row in decisions[-9:]],
            "posted_tail": [{key: row[key] for key in ("character", "decision")}
                            for row in posts[-9:]],
        })
    data = json.dumps({"captures": captures}, ensure_ascii=False, separators=(",", ":"))
    TARGET.write_bytes(gzip.compress(data.encode("utf-8"), mtime=0))
    print(f"{TARGET}: {len(captures)} captures, {TARGET.stat().st_size} bytes")


if __name__ == "__main__":
    extract()
