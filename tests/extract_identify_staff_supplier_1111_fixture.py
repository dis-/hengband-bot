"""Extract tests/fixtures/identify-staff-supplier-1111/<stop>/.

Source: the town:blocked:survival:identify_staff_ready incident captures of
n1-a life-508 on 2026-11-11 (copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/town-retired-burst-1110/n1-a-life-508/):

  n1a-508-0320  build bot-cfc720d28, 03:20 (incident-032007): journal rows
           0-19 (the stop on the next row).
  n1a-508-0419  build bot-d09fcc044, 04:19 (incident-0419): journal rows
           0-13 (the stop on the next row).

Each stop keeps its town-arrival checkpoint (``policy.pkl``), the journal rows
named above and the sidecar files the restored policy reads (base64), all
xz-compressed.  The loadout report (an append-only log the policy only
writes) is left out.

    python tests/extract_identify_staff_supplier_1111_fixture.py
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/town-retired-burst-1110/n1-a-life-508")
FIXTURES = Path(__file__).with_name("fixtures") / "identify-staff-supplier-1111"
STOPS = {
    "n1a-508-0320": (ROOT / "incident-032007/town-arrival", 20),
    "n1a-508-0419": (ROOT / "incident-0419/town-arrival", 14),
}
LEFT_OUT = {"_loadout_report_path"}
PRESET = 9 | lzma.PRESET_EXTREME


def main() -> None:
    for name, (visit, rows) in STOPS.items():
        target = FIXTURES / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "policy.pkl.xz").write_bytes(
            lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
        journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(True)
        (target / "journal.jsonl.xz").write_bytes(
            lzma.compress(b"".join(journal[:rows]), preset=PRESET))
        manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
        files = {}
        for role, entry in manifest.items():
            if role in LEFT_OUT:
                manifest[role] = {**entry, "copied": False, "reason": "left-out"}
            elif entry.get("copied"):
                files[role] = base64.b64encode((visit / "sidecars" / role).read_bytes()).decode("ascii")
        (target / "sidecars.json.xz").write_bytes(lzma.compress(json.dumps(
            {"manifest": manifest, "files": files}, ensure_ascii=False).encode("utf-8"),
            preset=PRESET))
        print(name, sorted(path.name for path in target.iterdir()))


if __name__ == "__main__":
    main()
