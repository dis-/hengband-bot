"""Extract tests/fixtures/n1b-370-me-staff-1112/.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-370-me-staff-1112/:

* ``arrival/``: n1-b life-370's no-key-exhausted of 2026-11-12 02:19:55
  (incident 20261112-021950, ``town-arrival``), rows 0-20 (row 20 is the
  chest drop on the Home entrance).
* ``restart/``: the first restart's quest:blocked:me-staff of 02:20
  (jsonlog/town-arrival/20261112-021959.379267029-turn9020561), its whole
  journal (five rows, the stop is row 4).

Each holds the town-arrival checkpoint (``policy.pkl``), the journal rows and
the sidecar files the restored policy reads (base64), all xz-compressed.  The loadout report (an append-only log the
policy only writes) is left out.

    python tests/extract_n1b_370_me_staff_1112_fixture.py
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

CAPTURES = Path("C:/hengband-backups/pdca/captures/n1b-370-me-staff-1112")
SOURCES = {
    "arrival": (CAPTURES / "20261112-021950-no-key-exhausted" / "town-arrival", 21),
    "restart": (CAPTURES / "restart-checkpoint-021959", 5),
}
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-370-me-staff-1112"
LEFT_OUT = {"_loadout_report_path"}
PRESET = 9 | lzma.PRESET_EXTREME


def main() -> None:
    for name, (visit, rows) in SOURCES.items():
        extract(visit, rows, FIXTURE / name)


def extract(visit: Path, rows: int, target: Path) -> None:
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
    print(sorted((path.name, path.stat().st_size) for path in target.iterdir()))


if __name__ == "__main__":
    main()
