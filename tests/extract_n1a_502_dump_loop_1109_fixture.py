"""Extract tests/fixtures/n1a-502-dump-loop-1109/.

Source: the viewing warrior n1-a life-502 (Lv27), the first of two loop-detected stops
of 2026-11-09 (21:24:40, twelve periodic:character-dump keys at turn 1016025), copied
read-only to C:/hengband-backups/pdca/captures/n1a-502-dump-loop-1109/:
20261109-212440-loop-detected (the incident capture, arrival turn 1015711).  Its
town-arrival checkpoint: the pickled arrival policy, the visit's journal cut to the rows
the test replays, the runtime sidecars (the character dump and calibration among them).

    python tests/extract_n1a_502_dump_loop_1109_fixture.py <incident-capture>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1a-502-dump-loop-1109"
# Rows 0-1 rest as recorded; row 2 is the first dump, row 3 the board after it.
ROWS = 4
PRESET = 9 | lzma.PRESET_EXTREME
# Sidecars the replay reads; the append-only loadout report is not one of them.
ROLES = ("_character_calibration_path", "_character_dump_path", "_confirmed_loadout_path",
         "_exploration_ledger.path", "_breeder_floor_record_path",
         "_overweight_surplus_ledger_path", "_town_visit_purchase_path", "_unseen_attack_path",
         "_home_disposal.history_path")


def main() -> None:
    visit = Path(sys.argv[1]) / "town-arrival"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (OUTPUT / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(journal[:ROWS]), preset=PRESET))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    manifest = {role: entry for role, entry in manifest.items() if role in ROLES}
    # Bytes as latin-1 text: the character dump is EUC-JP.
    sidecars = dict(manifest=manifest, files={
        role: (visit / "sidecars" / role).read_bytes().decode("latin-1")
        for role, entry in manifest.items() if entry.get("copied")})
    (OUTPUT / "sidecars.json.xz").write_bytes(lzma.compress(
        json.dumps(sidecars, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    for path in sorted(OUTPUT.iterdir()):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
