"""Extract tests/fixtures/idstaff-stockout-home-kit-1112/<stop>/.

Source: incident captures of n1-a life-512 on 2026-11-12 (copied read-only
from the viewing server to
C:/hengband-backups/pdca/captures/stops-1112-am/n1-a-life-512/):

  n1a-512-0720  town:blocked:survival:identify_staff_ready, build
           bot-a0789f5aa, 07:20 (incident-0720): journal rows 0-16 (the stop
           is row 16).
  n1a-512-0936  town:blocked:survival:home_atomic_withdraw_clear, build
           bot-6564ab9d1, 09:36 (incident-20261112-093643): rows 0-22 (the
           stop is row 22).
  n1a-512-0937  the same stop after the restart, 09:37
           (incident-20261112-093656): rows 0-25 (the stop is row 25).

Each stop keeps its town-arrival checkpoint (``policy.pkl``), the journal rows
named above and the sidecar files the restored policy reads (base64), all
xz-compressed.  The loadout report (an append-only log the policy only
writes) is left out.

    python tests/extract_idstaff_stockout_home_kit_1112_fixture.py
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/stops-1112-am/n1-a-life-512")
FIXTURES = Path(__file__).with_name("fixtures") / "idstaff-stockout-home-kit-1112"
STOPS = {
    "n1a-512-0720": (ROOT / "incident-0720/town-arrival", 17),
    "n1a-512-0936": (ROOT / "incident-20261112-093643/town-arrival", 23),
    "n1a-512-0937": (ROOT / "incident-20261112-093656/town-arrival", 26),
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
