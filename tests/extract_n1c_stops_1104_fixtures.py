"""Extract the n1-c stops of 2026-11-04 (stops-1104-0750, life-125 and life-127).

tests/fixtures/n1c-stops-1104/<stop>/: a town stop's arrival checkpoint and
visit journal, recompressed with xz.  tests/fixtures/n1c-stops-1104/boards.json.gz:
the dungeon boards of the life-125 berserk stuck prompt and D14 loop.

Only this extraction tool reads the captures; the committed test reads the
fixtures.
"""
import gzip
import json
import lzma
from pathlib import Path

from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_loops_0336_1102_fixtures import write


ROOT = Path("C:/hengband-backups/pdca/captures/stops-1104-0750/n1-c")
FIXTURES = Path(__file__).with_name("fixtures") / "n1c-stops-1104"
TOWN_STOPS = {
    "opening-fight": ROOT / "life-127/incident-captures/20261104-073130-quest-blocked-opening-route",
    "staff-inscription": ROOT / "life-127/incident-captures/20261104-073626-quest-blocked-me-staff",
}
BERSERK = ROOT / "life-125/incident-captures/20261104-064749-stuck-prompt"
LOOP = ROOT / "life-125/incident-captures/20261104-071817-loop-detected"
BERSERK_TURN = 778734
LOOP_TURNS = (923369, 923378, 923388, 923392)


def extract_town(name: str, capture: Path) -> None:
    target = FIXTURES / name
    target.mkdir(parents=True, exist_ok=True)
    visit = capture / "town-arrival"
    preset = 9 | lzma.PRESET_EXTREME
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))


def board(rows, turn):
    return [row for row in rows if row["type"] == "player_turn" and row["turn"] == turn][-1]


def skill(capture, generation):
    """The newest skill row of the named ring generation."""
    return [row for row in ring_rows(capture / "snapshots" / generation)
            if row["type"] == "knowledge" and row["knowledge"]["category"] == "skill_exp"][-1]


def main() -> None:
    for name, capture in TOWN_STOPS.items():
        extract_town(name, capture)
    berserk = ring_rows(BERSERK / "snapshots" / "snapshots-current.jsonl.gz")
    loop = ring_rows(LOOP / "snapshots" / "snapshots-current.jsonl.gz")
    state = json.loads((BERSERK / "policy-state.json").read_bytes())["state"]["_me_staff_sequence"]
    write(FIXTURES / "boards.json.gz", dict(
        source="snapshots-current of the life-125 stuck-prompt and loop-detected captures",
        berserk=dict(stop=board(berserk, BERSERK_TURN), skill=skill(BERSERK, "snapshots-20261104-064230-23018c.jsonl.gz"),
                     absorbed=state["absorbed"]),
        loop=dict(boards=[board(loop, turn) for turn in LOOP_TURNS], skill=skill(LOOP, "snapshots-current.jsonl.gz"))))


if __name__ == "__main__":
    main()
