"""Extract tests/fixtures/loops-1104/ from the 2026-11-04 morning loop stops.

Sources, under C:/hengband-backups/pdca/captures/stops-1104-morning/ (build
2d4b7645d / b044fd30f), only this tool reads them:

  n1-b/life-307/incident-captures/20261104-021407-loop-detected
      the ring's boards from the last sighted board (turn 376117) to the stop.
  n1-a/life-476/incident-captures/20261104-025135-loop-detected
  n1-b/life-307/incident-captures/20261104-031802-loop-detected
      the ring's last boards, the stop's remembered terrain and the retreat
      vetoes it held.

    PYTHONPATH="src;tests;." python tests/extract_loops_1104_fixtures.py
"""
import json
import lzma
from pathlib import Path

from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/stops-1104-morning")
BLIND = ROOT / "n1-b/life-307/incident-captures/20261104-021407-loop-detected"
ENCLOSED = {
    "enclosed-d15.json.xz": ROOT / "n1-a/life-476/incident-captures/20261104-025135-loop-detected",
    "enclosed-d18.json.xz": ROOT / "n1-b/life-307/incident-captures/20261104-031802-loop-detected",
}
OUTPUT = Path(__file__).with_name("fixtures") / "loops-1104"
TERRAIN = ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t",
           "upstairs", "downstairs")
PRESET = 9 | lzma.PRESET_EXTREME


def write(name: str, data: object) -> None:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    (OUTPUT / name).write_bytes(lzma.compress(payload, preset=PRESET))


def boards(capture: Path) -> list[dict]:
    return [row for row in ring_rows((capture / "snapshots/snapshots-current.jsonl.gz").read_bytes())
            if row["type"] == "player_turn"]


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    write("blind-air.json.xz", {"boards": [row for row in boards(BLIND) if row["turn"] >= 376117]})
    for name, capture in ENCLOSED.items():
        captured = json.loads((capture / "policy-state.json").read_text(encoding="utf-8"))
        write(name, {
            "boards": boards(capture)[-12:],
            "terrain": {key: captured["terrain"][key] for key in TERRAIN},
            "avoid": captured["state"]["_engagement_avoid_cells"],
            "probed": captured["state"]["_probed_frontiers"],
        })
    for path in sorted(OUTPUT.iterdir()):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
