"""Extract tests/fixtures/n1c-214-overextend-1115/.

Source: n1-c life-214 (Lv38 Magic-Eater, Angband 49F), copied read-only from the viewing server
to C:/hengband-backups/pdca/overextend-1115/ on 2026-11-15:

- the town-arrival checkpoint 20261115-170745.397880470-turn5269763 (the arrival after the
  Angband 49F dive of turns 5268291-5269763) and its journal row 0, the arrival board;
- dive-packs.json.xz, written on the server by server_dive_packs.py (kept beside it) from the
  life's raw snapshots and the decision digest of 17:07 (digest_n1c214.py): for seven Angband
  49F dives of 16:00-16:18 (turns 4813671-4970782), the carried inventory and equipment of the
  dive's first board, of every board on which the carried units by (tval, sval) changed or that
  followed a pickup decision (with the reason decided just before it), and of the arrival; the
  dive's counted escapes (the increments of the logged ``over_extension.dive_emergencies``) and
  pickup decisions; and the first raw board of the 17:07 checkpoint's own dive (turn 5268291),
  the dungeon board the replay carries those packs on.

    PYTHONPATH="src;tests" python tests/extract_n1c_214_overextend_1115_fixture.py
"""
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

SOURCE = Path("C:/hengband-backups/pdca/overextend-1115")
VISIT = SOURCE / "20261115-170745.397880470-turn5269763"
TARGET = Path(__file__).with_name("fixtures") / "n1c-214-overextend-1115"
DIVES = ("d64", "d65", "d66", "d67", "d73", "d74", "d75")


def main() -> None:
    extract(VISIT, TARGET, 1, frozenset({"_loadout_report_path"}))
    packs = json.loads(lzma.decompress((SOURCE / "dive-packs.json.xz").read_bytes()))
    kept = {"template": packs["_template_dungeon"]}
    for name in DIVES:
        dive = packs[name]
        states = dive["states"]
        # The arrival: the first town board (the stay's later boards are not the dive's).
        arrival = next(index for index, state in enumerate(states) if state["town"])
        kept[name] = {key: dive[key] for key in ("escapes", "pickup_decisions", "time")}
        kept[name]["states"] = states[:arrival + 1]
    (TARGET / "dives.json.xz").write_bytes(lzma.compress(
        json.dumps(kept, ensure_ascii=False, sort_keys=True).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
