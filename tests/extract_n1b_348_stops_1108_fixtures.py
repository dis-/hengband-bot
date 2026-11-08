"""Extract tests/fixtures/n1b-348-stops-1108/.

Source: the viewing Magic-Eater n1-b life-348 (Lv35, build bot-206702cc9), two stops of
2026-11-08 copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-348-1108/:

- ``a``: incident-captures/20261108-151642-town-blocked-owner-retired-burst
  (copied as incidentA/): its town-arrival checkpoint (the pickled arrival policy, the
  visit's journal cut to the rows the tests replay, the runtime sidecars).
- ``b``: captures/20261108-143713-loop-detected (copied as 20261108-143713-loop-detected/):
  state.jsonl.gz (the 38 boards of turns 2779359-2779728 at Orc cave 23F), the decision
  rows of those turns and the monster knowledge (lib/edit/MonraceDefinitions.jsonc) of
  every race on them.
- ``c``: n1-c life-171 (Magic-Eater Lv46, build bot-206702cc9) captures of the 16:59:51
  loop-detected stop at Angband 80F, copied to C:/hengband-backups/pdca/captures/
  n1c-171-80f-loop-1108/: its 68 boards (turns 3660848-3661310), their decision rows and
  the monster knowledge of every race on them.

    python tests/extract_n1b_348_stops_1108_fixtures.py <copies-root> <n1c-171-copy>
"""
import gzip
import json
import lzma
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import load_monrace_knowledge

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-348-stops-1108"
GAME = Path("C:/hengband/lib/edit")
A_ROWS = 4
PRESET = 9 | lzma.PRESET_EXTREME


def extract_a(capture: Path) -> None:
    visit = capture / "town-arrival"
    target = OUTPUT / "a"
    target.mkdir(parents=True, exist_ok=True)
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (target / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(journal[:A_ROWS]), preset=PRESET))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    # Bytes as latin-1 text: the character dump is EUC-JP.
    sidecars = dict(manifest=manifest, files={
        role: (visit / "sidecars" / role).read_bytes().decode("latin-1")
        for role, entry in manifest.items() if entry.get("copied")})
    (target / "sidecars.json.xz").write_bytes(lzma.compress(
        json.dumps(sidecars, ensure_ascii=False).encode("utf-8"), preset=PRESET))


def rows(path: Path) -> list:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def extract_loop(capture: Path, name: str) -> None:
    boards = [board for board in rows(capture / "state.jsonl.gz")
              if board.get("type") == "player_turn"]
    turns = {board["turn"] for board in boards}
    decisions = [{"turn": row["turn"], "reason": row["reason"], "key": row["key"]}
                 for row in rows(capture / "bot-decisions.jsonl.gz")
                 if row.get("turn") in turns and row.get("reason") != "loop-detected"]
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    ids = {row["race_id"] for board in boards
           for field in ("visible_monsters", "detected_monsters") for row in board.get(field, [])}
    fixture = {"boards": boards, "decisions": decisions,
               "monraces": {key: asdict(races[key]) for key in sorted(ids)}}
    with gzip.open(OUTPUT / f"{name}.json.gz", "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))


def main() -> None:
    root = Path(sys.argv[1])
    extract_a(root / "incidentA")
    extract_loop(root / "20261108-143713-loop-detected", "b")
    extract_loop(Path(sys.argv[2]), "c")
    for path in sorted(OUTPUT.rglob("*")):
        if path.is_file():
            print(path.relative_to(OUTPUT), path.stat().st_size)


if __name__ == "__main__":
    main()
