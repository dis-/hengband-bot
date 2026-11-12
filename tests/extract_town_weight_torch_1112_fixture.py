"""Extract tests/fixtures/town-weight-torch-1112/.

Source: the incident captures of n1-c life-202 on 2026-11-12 (copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/evening-1112/n1-c/life-202/):

  incident-captures/20261112-171825-town-blocked-survival-inventory_weight_ready
      the stop visit: its town-arrival checkpoint (``policy.pkl``), the visit journal
      (rows 0-143; the stop is row 143) and the sidecar files the restored policy reads.
  incident-captures/20261112-171837-town-blocked-survival-inventory_weight_ready
      only its sidecar character dump: the restarted process's arrival copied the dump the
      stop visit's row 1 (``periodic:character-dump``) wrote (AC 30, as the boards; the stop
      visit's own copy is the earlier AC 38 dump taken at its arrival).

All xz-compressed; the sidecars as base64 in one JSON.  The loadout report (an
append-only log the policy only writes) is left out.

    python tests/extract_town_weight_torch_1112_fixture.py
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/evening-1112/n1-c/life-202/incident-captures")
VISIT = ROOT / "20261112-171825-town-blocked-survival-inventory_weight_ready" / "town-arrival"
ROW1_DUMP = (ROOT / "20261112-171837-town-blocked-survival-inventory_weight_ready"
             / "town-arrival" / "sidecars" / "_character_dump_path")
ROWS = 144
FIXTURE = Path(__file__).with_name("fixtures") / "town-weight-torch-1112"
LEFT_OUT = {"_loadout_report_path"}
PRESET = 9 | lzma.PRESET_EXTREME


def main() -> None:
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "policy.pkl.xz").write_bytes(
        lzma.compress((VISIT / "policy.pkl").read_bytes(), preset=PRESET))
    rows = gzip.decompress((VISIT / "journal.jsonl.gz").read_bytes()).splitlines(True)
    (FIXTURE / "journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(rows[:ROWS]), preset=PRESET))
    manifest = json.loads((VISIT / "sidecars.json").read_text(encoding="utf-8"))
    files = {}
    for role, entry in manifest.items():
        if role in LEFT_OUT:
            manifest[role] = {**entry, "copied": False, "reason": "left-out"}
        elif entry.get("copied"):
            files[role] = base64.b64encode((VISIT / "sidecars" / role).read_bytes()).decode("ascii")
    (FIXTURE / "sidecars.json.xz").write_bytes(lzma.compress(json.dumps(
        {"manifest": manifest, "files": files}, ensure_ascii=False).encode("utf-8"),
        preset=PRESET))
    (FIXTURE / "dump-after-row1.txt.xz").write_bytes(
        lzma.compress(ROW1_DUMP.read_bytes(), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
