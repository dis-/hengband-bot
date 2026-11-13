"""Extract the fixtures of the 2026-11-13 morning viewing stops.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/viewing-stops-1113am:

 - ``arrival`` -- an incident capture's ``town-arrival`` directory (policy.pkl,
   journal.jsonl.gz, sidecars/_character_calibration_path), recompressed with xz into
   tests/fixtures/viewing-stops-1113/<name>/:
     opening-385  n1-b life-385 20261113-084413-quest-blocked-opening-route
     opening-387  n1-b life-387 20261113-123022-quest-blocked-opening-route
     kill-mob-389 n1-b life-389 jsonlog/town-arrival/20261113-140656.143744541-turn3456705,
                  the first 140 journal rows (the live journal reached its 16 MiB cap)

    python tests/extract_viewing_stops_1113_fixtures.py arrival <town-arrival directory> <name> [rows]

 - ``boards`` -- the last ``count`` distinct boards (turn, position) of a stop capture's
   state.jsonl.gz, into tests/fixtures/viewing-stops-1113/<name>.json.xz ({"boards": [...]}):
     fire-target-519  n1-a life-519 20261113-111657-stall-floor-dwell-ranged-fire-target, 6
     explore-loot-205 n1-c life-205 20261113-091554-stall-floor-dwell-explore, 40
     summoner-edge-205 n1-c life-205 20261113-105844-loop-detected, 40

    python tests/extract_viewing_stops_1113_fixtures.py boards <state.jsonl.gz> <name> <count>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "viewing-stops-1113"
PRESET = 9 | lzma.PRESET_EXTREME


def arrival(source: Path, name: str, rows: int | None = None) -> None:
    target = FIXTURES / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((source / "policy.pkl").read_bytes(), preset=PRESET))
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(_journal(source, rows), preset=PRESET))
    (target / "calibration.json").write_bytes(
        (source / "sidecars" / "_character_calibration_path").read_bytes())


def _journal(source: Path, rows: int | None) -> bytes:
    raw = gzip.decompress((source / "journal.jsonl.gz").read_bytes())
    if rows is None:
        return raw
    return b"".join(raw.splitlines(keepends=True)[:rows])


def boards(source: Path, name: str, count: int) -> None:
    rows, seen = [], set()
    with gzip.open(source, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            row = json.loads(line)
            if "grid_map" not in row or "player" not in row:
                continue
            key = (row["turn"], row["player"].get("y"), row["player"].get("x"))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{name}.json.xz").write_bytes(lzma.compress(json.dumps(
        {"boards": rows[-count:]}, ensure_ascii=False).encode("utf-8", "surrogateescape"),
        preset=PRESET))


def main() -> None:
    kind = sys.argv[1]
    if kind == "arrival":
        arrival(Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else None)
    elif kind == "boards":
        boards(Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]))
    else:
        raise SystemExit(f"unknown kind {kind}")


if __name__ == "__main__":
    main()
