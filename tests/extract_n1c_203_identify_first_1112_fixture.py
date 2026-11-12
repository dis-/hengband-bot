"""Extract tests/fixtures/n1c-203-identify-first-1112/<stop>/.

Source: the incident captures of n1-c life-203 on 2026-11-12 (the viewing server's
~/hengbot-soak/n1-c/life-203/incident-captures/, copied read-only into a scratch
folder; pass it as the argument):

  n1c-203-2238  20261112-223843-town-blocked-survival-recall_departure_ready
                (journal rows 0-71; the stop is row 71)
  n1c-203-2239  20261112-223855-town-blocked-survival-recall_departure_ready
                (the restarted process; rows 0-11, the stop is row 11)

Each stop keeps its town-arrival checkpoint (``policy.pkl``), the journal rows and the
sidecar files the restored policy reads (base64), xz-compressed; the loadout report is
left out.  ``dump-after-dump-row.txt.xz``: the character dump the game wrote at the
stop's ``periodic:character-dump`` row, i.e. the next process's arrival copy (22:38:53
for the first stop, 22:39:05 for the second).

    python tests/extract_n1c_203_identify_first_1112_fixture.py <incident-captures dir>
"""
import base64
import gzip
import json
import lzma
import sys
from pathlib import Path

STOPS = {
    "n1c-203-2238": ("20261112-223843-town-blocked-survival-recall_departure_ready", 72,
                     "20261112-223855-town-blocked-survival-recall_departure_ready"),
    "n1c-203-2239": ("20261112-223855-town-blocked-survival-recall_departure_ready", 12,
                     "20261112-223908-town-blocked-survival-recall_departure_ready"),
}
FIXTURES = Path(__file__).with_name("fixtures") / "n1c-203-identify-first-1112"
LEFT_OUT = {"_loadout_report_path"}
PRESET = 9 | lzma.PRESET_EXTREME


def main(root: Path) -> None:
    for name, (capture, rows, next_capture) in STOPS.items():
        visit = root / capture / "town-arrival"
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
        dump = root / next_capture / "town-arrival" / "sidecars" / "_character_dump_path"
        (target / "dump-after-dump-row.txt.xz").write_bytes(
            lzma.compress(dump.read_bytes(), preset=PRESET))
        print(name, sorted((path.name, path.stat().st_size) for path in target.iterdir()))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
