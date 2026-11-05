"""Extract tests/fixtures/launcher-sale-1106/ for test_launcher_sale_1106_recorded.

Source: n1-b life-322, 2026-11-06 (build bot-f67755a8f), copied to
C:/hengband-backups/pdca/captures/launcher-sale-1106/.  The Q14 reward, an
unidentified Light Crossbow, was sold to the Weapon Smith at 02:37:13
(decision 13949 shop:in-store-inscribe {o@0, 13950 shop:in-store-sell d0y).
That visit's own arrival checkpoint was pruned; the nearest one is the
town-arrival of the 02:43 loop-detected incident capture (02:37:31, turn
944522, the next arrival), kept here with its character calibration.  The
boards are the recorded snapshots of the sale (turn 941803: outside the Smith
and its page before the inscription) and of the same stay after the Alchemist
identified the devices (turn 943434).

    python tests/extract_launcher_sale_1106_fixture.py <captures/launcher-sale-1106>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "launcher-sale-1106"
SNAPSHOTS = "snapshots-20261106-025009-a57e07.jsonl.gz"
ARRIVAL = "arrival-0237/town-arrival"
BOARDS = {"outside-smith": (941803, False), "smith-page": (941803, True),
          "after-identify": (943434, False)}


def boards(path: Path) -> dict:
    found: dict = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            board = json.loads(line)
            for name, (turn, in_store) in BOARDS.items():
                if (name not in found and board["turn"] == turn
                        and bool(board.get("store")) == in_store
                        and board.get("type") in ("store", "player_turn")):
                    found[name] = board
    return found


def main() -> None:
    root = Path(sys.argv[1])
    visit = root / ARRIVAL
    FIXTURE.mkdir(parents=True, exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (FIXTURE / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (FIXTURE / "calibration.json").write_bytes(
        (visit / "sidecars" / "_character_calibration_path").read_bytes())
    found = boards(root / SNAPSHOTS)
    assert set(found) == set(BOARDS), sorted(found)
    (FIXTURE / "boards.json.xz").write_bytes(lzma.compress(
        json.dumps(found, ensure_ascii=False).encode("utf-8"), preset=preset))


if __name__ == "__main__":
    main()
