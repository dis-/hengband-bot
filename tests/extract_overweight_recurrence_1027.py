"""Freeze the #98 viewing stops, without changing a captured board.

The current snapshot ring can start inside a gzip member. Read complete members,
discard only incomplete JSON lines, and retain its final board, last Home page
and last Home knowledge. Decisions supply retention, depth and route evidence;
the diagnostic state supplies the first capture's purchase reservations.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import zlib


ROOT = Path(__file__).resolve().parents[1]
CAPTURES = Path("C:/hengband-backups/viewing-captures-1027")
NAMES = (
    "20261027-011308-town-blocked-overweight-home-full-no-legal-relief",
    "20261026-231603-town-blocked-overweight-home-unreachable",
)
OUTPUT = ROOT / "tests/fixtures/overweight-recurrence-1027.json.gz"


def ring_rows(path):
    raw = path.read_bytes()
    magic = b"\x1f\x8b\x08"
    offset = raw.find(magic)
    while 0 <= offset < len(raw):
        engine = zlib.decompressobj(31)
        try:
            decoded = engine.decompress(raw[offset:])
        except zlib.error:
            decoded = b""
        if not decoded or not engine.eof:
            offset = raw.find(magic, offset + 1)
            continue
        offset = len(raw) - len(engine.unused_data)
        for line in decoded.splitlines():
            try:
                yield json.loads(line)
            except ValueError:
                continue


def main():
    captures = []
    for name in NAMES:
        directory = CAPTURES / name
        ring = directory / ("snapshots/snapshots-current.jsonl.gz"
                            if (directory / "snapshots").exists() else "state.jsonl.gz")
        tail = directory / ("decision-tail.jsonl" if (directory / "decision-tail.jsonl").exists()
                            else "bot-decisions.jsonl.gz")
        home = knowledge = board = None
        for row in ring_rows(ring):
            board = row
            if row.get("knowledge", {}).get("category") == "home":
                knowledge = row
            if row.get("store", {}).get("store_type") == 7:
                home = row
        opener = gzip.open if tail.suffix == ".gz" else open
        decisions = []
        with opener(tail, "rt", encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if "decision_sequence" in row:
                    decisions.append(row)
        last = decisions[-1]
        assert board["turn"] == last["turn"]
        sources = [ring, tail]
        purchases = []
        state_path = directory / "policy-state.json"
        if state_path.exists():
            sources.append(state_path)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            purchases = state["modes_and_latches"]["_town_visit_purchase_record"]
        captures.append(dict(
            capture=name, board=board, home=home, knowledge=knowledge,
            purchases=purchases,
            decisions=[{key: row.get(key) for key in (
                "decision_sequence", "turn", "reason", "key", "retention_reservations",
                "procurement_requirements", "equipment_optimization", "fundraising")}
                for row in decisions[-20:]],
            sources={str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sources},
        ))
    OUTPUT.write_bytes(gzip.compress(json.dumps(captures, ensure_ascii=False).encode("utf-8"), mtime=0))
    print(OUTPUT.name, OUTPUT.stat().st_size, hashlib.sha256(OUTPUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
