"""Extract tests/fixtures/me-int-loadout-1108/ for test_me_int_loadout_recorded.

Source: n1-b life-339 (viewing server, 2026-11-08), the town-arrival
checkpoint jsonlog/town-arrival/20261108-010513.686659623-turn2112580
(Magic-Eater Lv29, ☆『ラバー・コート』 worn, ★『ホルヘンネス』 (+2 INT) on the
Home shelf since the 00:48 home:weight-overload-deposit).
- ``policy.pkl.xz``: the arrival checkpoint.
- ``journal.jsonl.xz``: its journal cut to rows 0-17 (rows 9-15 scan the
  Home; the equipment optimizer then runs on the complete catalog).
- ``sidecars.json.xz``: its runtime sidecars with their manifest.

    python tests/extract_me_int_loadout_fixture.py <town-arrival-visit-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "me-int-loadout-1108"
JOURNAL_ROWS = 18


def main() -> None:
    visit = Path(sys.argv[1])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (OUTPUT / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (OUTPUT / "journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(journal[:JOURNAL_ROWS]), preset=preset))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    # Bytes as latin-1 text: the character dump is EUC-JP.
    sidecars = dict(manifest=manifest, files={
        role: (visit / "sidecars" / role).read_bytes().decode("latin-1")
        for role, entry in manifest.items() if entry.get("copied")})
    (OUTPUT / "sidecars.json.xz").write_bytes(lzma.compress(
        json.dumps(sidecars, ensure_ascii=False).encode("utf-8"), preset=preset))
    for path in sorted(OUTPUT.iterdir()):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
