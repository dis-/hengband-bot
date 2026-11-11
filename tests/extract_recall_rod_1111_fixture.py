"""Extract tests/fixtures/recall-rod-1111/n1a-508-0040/.

Source: n1-a life-508's town:blocked:owner-retired-burst incident capture of
2026-11-11 00:40 (incident-004001), copied read-only from
the viewing server to
C:/hengband-backups/pdca/captures/town-retired-burst-1110/n1-a-life-508/:
its town-arrival checkpoint (``policy.pkl``), journal rows 0-13 (row 13 is the
first town:recall-stockout-mining) and the sidecar files the restored policy
reads (base64), all xz-compressed.  The loadout report (an append-only log the
policy only writes) is left out.

    python tests/extract_recall_rod_1111_fixture.py
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

VISIT = Path("C:/hengband-backups/pdca/captures/town-retired-burst-1110/n1-a-life-508"
             "/incident-004001/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "recall-rod-1111" / "n1a-508-0040"
ROWS = 14
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
