"""Extract tests/fixtures/n1b-359-overflow-1109/.

Source: the viewing Magic-Eater n1-b life-359 (Lv37), the town-arrival
checkpoint of the first town:blocked:overflow-no-legal-disposal stop of
2026-11-09 20:20:27 (arrival 20:20:16, turn 3365213, build a0b7b8e7b), copied
read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-359-overflow-1109/20261109-202027-town-blocked-overflow-no-legal-disposal/town-arrival/.

It keeps the pickled arrival policy, the whole visit journal (rows 0-13;
row 13 is the stop) and the runtime sidecars with their manifest.

    python tests/extract_n1b_359_overflow_1109_fixture.py <town-arrival-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-359-overflow-1109"


def main() -> None:
    visit = Path(sys.argv[1])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (OUTPUT / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    (OUTPUT / "journal.jsonl.xz").write_bytes(
        lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    # Bytes as latin-1 text: the character dump is EUC-JP.
    files = {role: (visit / "sidecars" / role).read_bytes().decode("latin-1")
             for role, entry in manifest.items() if entry.get("copied")}
    (OUTPUT / "sidecars.json.xz").write_bytes(lzma.compress(
        json.dumps(dict(manifest=manifest, files=files), ensure_ascii=False).encode("utf-8"),
        preset=preset))
    for path in sorted(OUTPUT.iterdir()):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
