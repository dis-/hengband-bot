"""Extract tests/fixtures/n1b-377-pile-loot-1112/.

Source: n1-b life-377's town:blocked:owner-retired-burst of 2026-11-12 11:13
(incident 20261112-111325), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-377-pile-loot-1112/20261112-111325-town-blocked-owner-retired-burst:
its town-arrival checkpoint (``policy.pkl``), journal rows 0-283 (row 283 is
the first board on the armour pile of the loop) and the sidecar files the
restored policy reads (base64), all xz-compressed.  The loadout report (an
append-only log the policy only writes) is left out.

    python tests/extract_n1b_377_pile_loot_1112_fixture.py
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

VISIT = Path("C:/hengband-backups/pdca/captures/n1b-377-pile-loot-1112"
             "/20261112-111325-town-blocked-owner-retired-burst/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1b-377-pile-loot-1112"
ROWS = 284
LEFT_OUT = {"_loadout_report_path"}
PRESET = 9 | lzma.PRESET_EXTREME


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "policy.pkl.xz").write_bytes(
        lzma.compress((VISIT / "policy.pkl").read_bytes(), preset=PRESET))
    journal = gzip.decompress((VISIT / "journal.jsonl.gz").read_bytes()).splitlines(True)
    (TARGET / "journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(journal[:ROWS]), preset=PRESET))
    manifest = json.loads((VISIT / "sidecars.json").read_text(encoding="utf-8"))
    files = {}
    for role, entry in manifest.items():
        if role in LEFT_OUT:
            manifest[role] = {**entry, "copied": False, "reason": "left-out"}
        elif entry.get("copied"):
            files[role] = base64.b64encode((VISIT / "sidecars" / role).read_bytes()).decode("ascii")
    (TARGET / "sidecars.json.xz").write_bytes(lzma.compress(json.dumps(
        {"manifest": manifest, "files": files}, ensure_ascii=False).encode("utf-8"),
        preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
