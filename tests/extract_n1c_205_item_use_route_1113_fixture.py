"""Extract tests/fixtures/n1c-205-item-use-route-1113/<name>/.

Source: n1-c life-205's town-arrival checkpoints on the viewing server
(~/hengbot-soak/n1-c/life-205/jsonlog/town-arrival/, copied read-only to
C:/hengband-backups/pdca/captures/n1c-205-item-audit-1113/):

 * ``v1329`` - 20261113-132930.164543265-turn4048445 (Lv45, the Home list current at the
   arrival), rows 0-13: row 8 is the Magic shop page after the recorded sale, row 13 the
   Alchemist page where the recorded bot bought Teleportation;
 * ``v1336`` - 20261113-133618.713746228-turn4066451, rows 0-3: row 3 is the Home page whose
   weight-overload deposit shelved the Remove Curse scroll.

The checkpoint (``policy.pkl``), the journal rows and the sidecar files the restored policy
reads (base64), xz-compressed; the loadout report is left out.

    python tests/extract_n1c_205_item_use_route_1113_fixture.py <town-arrival dir> <name> <rows>
"""
import base64
import gzip
import json
import lzma
import sys
from pathlib import Path

ROOT = Path(__file__).with_name("fixtures") / "n1c-205-item-use-route-1113"
LEFT_OUT = {"_loadout_report_path"}
PRESET = 9 | lzma.PRESET_EXTREME


def main(visit: Path, name: str, rows: int) -> None:
    fixture = ROOT / name
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
    lines = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(True)
    (fixture / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(lines[:rows]), preset=PRESET))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    files = {}
    for role, entry in manifest.items():
        if role in LEFT_OUT:
            manifest[role] = {**entry, "copied": False, "reason": "left-out"}
        elif entry.get("copied"):
            files[role] = base64.b64encode((visit / "sidecars" / role).read_bytes()).decode("ascii")
    (fixture / "sidecars.json.xz").write_bytes(lzma.compress(json.dumps(
        {"manifest": manifest, "files": files}, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in fixture.iterdir()))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
