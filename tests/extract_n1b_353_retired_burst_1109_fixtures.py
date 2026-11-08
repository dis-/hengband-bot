"""Extract tests/fixtures/n1b-353-retired-burst-1109/.

Source: the viewing Magic-Eater n1-b life-353 (Lv37, the resumed life-348, build
bot-4454608e3), the third of three town:blocked:owner-retired-burst stops of 2026-11-08
(23:20:30, 23:20:47, 23:21:04), copied read-only to
C:/hengband-backups/pdca/captures/n1b-353-retired-burst-1109/:
20261108-232059-town-blocked-owner-retired-burst (the incident capture of the third
process, arrival turn 3827905).  Its town-arrival checkpoint: the pickled arrival policy,
the visit's journal cut to the rows the tests replay, the runtime sidecars.

    python tests/extract_n1b_353_retired_burst_1109_fixtures.py <incident-capture>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-353-retired-burst-1109"
# Rows 0-19 decide as recorded; row 20 is the first absorbed Identify cast.
ROWS = 21
PRESET = 9 | lzma.PRESET_EXTREME


def main() -> None:
    visit = Path(sys.argv[1]) / "town-arrival"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (OUTPUT / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(journal[:ROWS]), preset=PRESET))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
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
