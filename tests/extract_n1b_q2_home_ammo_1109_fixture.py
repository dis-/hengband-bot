"""Extract tests/fixtures/n1b-q2-home-ammo-1109/.

Source: the viewing Magic-Eater n1-b life-354 (Lv28, light crossbow), the
town-arrival checkpoint written at 2026-11-09 01:59:40 (turn 1453652), copied
read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-354-q2-ammo-1109/20261109-015940.177263859-turn1453652/.

It keeps the pickled arrival policy, the visit's journal cut to the rows the
test replays (rows 0-27; row 25's responses carry the ``~9`` Home catalogue)
and the runtime sidecars with their manifest.

    python tests/extract_n1b_q2_home_ammo_1109_fixture.py <town-arrival-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-q2-home-ammo-1109"
ROWS = 28


def main() -> None:
    visit = Path(sys.argv[1])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (OUTPUT / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (OUTPUT / "journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(journal[:ROWS]), preset=preset))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    # Bytes as latin-1 text: the character dump is EUC-JP.  The loadout
    # report (7.8 MB, append-only history) is not read by the replayed rows.
    manifest["_loadout_report_path"] = dict(
        manifest["_loadout_report_path"], copied=False, reason="fixture-omitted")
    files = {role: (visit / "sidecars" / role).read_bytes().decode("latin-1")
             for role, entry in manifest.items() if entry.get("copied")}
    (OUTPUT / "sidecars.json.xz").write_bytes(lzma.compress(
        json.dumps(dict(manifest=manifest, files=files), ensure_ascii=False).encode("utf-8"),
        preset=preset))
    for path in sorted(OUTPUT.iterdir()):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
