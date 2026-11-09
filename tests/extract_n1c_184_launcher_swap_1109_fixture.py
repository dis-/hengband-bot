"""Extract tests/fixtures/n1c-184-launcher-swap-1109/.

Source: the viewing Magic-Eater n1-c life-184 (Lv23, bot-b4dec292b), the
town-arrival checkpoint written at 2026-11-09 22:00:28 (turn 1312263) and
kept by the loop-detected incident capture of 22:03:38, copied read-only from
the viewing server to
C:/hengband-backups/pdca/captures/n1c-184-launcher-swap-1109/incident-captures/20261109-220338-loop-detected/town-arrival/.

It keeps the pickled arrival policy, the visit's journal cut to the rows the
test replays (rows 0-43; row 43's responses carry the ``~9`` Home catalogue)
and the runtime sidecars with their manifest.

    python tests/extract_n1c_184_launcher_swap_1109_fixture.py <town-arrival-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1c-184-launcher-swap-1109"
ROWS = 44


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
    # report (3.5 MB, append-only history) is not read by the replayed rows.
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
