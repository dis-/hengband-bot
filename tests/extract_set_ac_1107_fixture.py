"""Extract tests/fixtures/set-ac-1107/.

Source: n1-b life-338 (viewing server, 2026-11-07), the town-arrival
checkpoint jsonlog/town-arrival/20261107-203856.519926566-turn2173221 (Lv34,
★二天一流開祖宮本武蔵の脇差し in main_hand, a small metal shield in sub_hand,
★ロヒアリムの金属製ブリガンダイン・アーマー on the Home shelf since 20:15).
- ``policy.pkl.xz``: the arrival checkpoint.
- ``journal.jsonl.xz``: its journal cut to rows 0-43 (row 42 posts the
  town character dump, row 43 decides on its C response).
- ``sidecars.json.xz``: its runtime sidecars with their manifest (the
  character dump written before the arrival among them).

    python tests/extract_set_ac_1107_fixture.py <town-arrival-visit-dir>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "set-ac-1107"
JOURNAL_ROWS = 44


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
