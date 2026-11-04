"""Extract tests/fixtures/open-stops-1104/ for test_open_stops_1104_recorded.

Source: C:/hengband-backups/pdca/captures/stops-1104-1330 (build bot-014ddb7dd).
boards.json.gz: the recorded dungeon boards of each stop.  home-take/: the n1-b
life-308 arrival checkpoint, calibration and visit journal, recompressed with xz.

Only this extraction tool reads the captures; the committed test reads the fixtures.
"""
import gzip
import json
import lzma
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


ROOT = Path("C:/hengband-backups/pdca/captures/stops-1104-1330")
FIXTURES = Path(__file__).with_name("fixtures") / "open-stops-1104"
HOME = ROOT / "n1-b/life-308/incident-captures/20261104-122340-stuck-prompt"
ESP_WALK = ROOT / "n1-a/life-477/incident-captures/20261104-085308-loop-detected"
ESP_WALK_TURNS = (933431, 933445, 933459)
DARK_WALK = ROOT / "n1-b/life-308/incident-captures/20261104-124224-loop-detected"
DARK_WALK_TURNS = (799998, 800012, 800021, 800026, 800036, 800045, 800049, 800059)
ZANTETSU = ROOT / "n1-b/life-307/captures/20261104-112313-stall-melee/state.jsonl.gz"
ACID = ROOT / "n1-a/life-478/incident-captures/20261104-104549-player-death"
ACID_TURN = 601910


def boards(capture, turns, generation="snapshots-current.jsonl.gz"):
    rows = ring_rows(capture / "snapshots" / generation)
    return [[row for row in rows if row["type"] == "player_turn" and row["turn"] == turn][-1]
            for turn in turns]


def floor_memory(capture):
    """What the policy remembered of the floor at the capture, by its state dump."""
    dump = json.loads((capture / "policy-state.json").read_bytes().decode("utf-8", "replace"))
    terrain, state = dump["terrain"], dump["state"]
    return dict(terrain={name: terrain[name] for name in ("known_t", "marked_t", "floor_t", "wall_t", "door_t", "rubble_t")},
                visits=state["_visit_counts"], probed=state["_probed_frontiers"])


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    state = gzip.decompress(ZANTETSU.read_bytes()).decode("euc_jp", "replace").splitlines()
    write(FIXTURES / "boards.json.gz", dict(
        source="stops-1104-1330: life-477 and life-308 loop-detected, life-307 stall-melee, life-478 death",
        esp_walk=boards(ESP_WALK, ESP_WALK_TURNS),
        dark_walk=boards(DARK_WALK, DARK_WALK_TURNS),
        zantetsu=json.loads(state[-1]),
        acid=boards(ACID, (ACID_TURN,))[0],
        acid_memory=floor_memory(ACID)))
    target = FIXTURES / "home-take"
    target.mkdir(exist_ok=True)
    visit = HOME / "town-arrival"
    preset = 9 | lzma.PRESET_EXTREME
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))
    (target / "calibration.json").write_bytes(
        (visit / "sidecars" / "_character_calibration_path").read_bytes())


if __name__ == "__main__":
    main()
