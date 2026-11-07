"""Extract the 2026-11-07 fixtures of the detected-monster route and hunt-walk fixes.

Sources, copied read-only from the viewing server to C:/hengband-backups (or a scratch copy):

 - ``hunt`` -- n1-b life-335 jsonlog/snapshots/snapshots-current.jsonl.gz (Angband 24F,
   RANDOM quest 41): the player_turn rows of turns 1835560..1835660, the 『アルベリヒ』
   walk that stepped between (31,50) and (32,50); plus the last skill list
   (``skill_exp``) the live process read before them.
   Output: tests/fixtures/detected-hunt-335-1107.json.xz ({"skill": ..., "boards": [...]}).
 - ``opening`` -- n1-b life-336's incident capture
   20261107-090551-quest-blocked-opening-route/town-arrival (policy.pkl, journal.jsonl.gz,
   sidecars/_character_calibration_path), recompressed with xz.
   Output: tests/fixtures/opening-route-336-1107/.

    python tests/extract_detected_hunt_1107_fixtures.py hunt <snapshots .jsonl.gz>
    python tests/extract_detected_hunt_1107_fixtures.py opening <town-arrival directory>
"""
import gzip
import json
import lzma
import re
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures")
PRESET = 9 | lzma.PRESET_EXTREME
HUNT_TURNS = (1835560, 1835660)
TURN = re.compile(rb'"turn":\s*(\d+)')


def _window(path: Path, first: int, last: int) -> dict:
    boards, skill = {}, None
    with gzip.open(path, "rb") as stream:
        for line in stream:
            if not line.startswith(b"{"):
                continue
            match = TURN.search(line)
            turn = int(match.group(1)) if match else -1
            if b'"skill_exp"' in line and turn <= last:
                skill = json.loads(line)
            if b'"player_turn"' not in line or not first <= turn <= last:
                continue
            row = json.loads(line)
            if row.get("type") == "player_turn":
                boards.setdefault(row["turn"], line.decode("utf-8", "surrogateescape").rstrip("\n"))
    return {"skill": skill, "boards": [boards[turn] for turn in sorted(boards)]}


def _write(name: str, payload: dict) -> None:
    (FIXTURES / name).write_bytes(lzma.compress(
        json.dumps(payload, ensure_ascii=False).encode("utf-8", "surrogateescape"), preset=PRESET))


def main() -> None:
    kind, source = sys.argv[1], Path(sys.argv[2])
    if kind == "hunt":
        _write("detected-hunt-335-1107.json.xz", _window(source, *HUNT_TURNS))
    elif kind == "opening":
        target = FIXTURES / "opening-route-336-1107"
        target.mkdir(parents=True, exist_ok=True)
        (target / "policy.pkl.xz").write_bytes(
            lzma.compress((source / "policy.pkl").read_bytes(), preset=PRESET))
        (target / "journal.jsonl.xz").write_bytes(
            lzma.compress(gzip.decompress((source / "journal.jsonl.gz").read_bytes()), preset=PRESET))
        (target / "calibration.json").write_bytes(
            (source / "sidecars" / "_character_calibration_path").read_bytes())
    else:
        raise SystemExit(f"unknown kind {kind}")


if __name__ == "__main__":
    main()
