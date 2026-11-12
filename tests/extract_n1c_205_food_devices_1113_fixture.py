"""Extract tests/fixtures/n1c-205-food-devices-1113/.

Source: n1-c life-205's incident capture 20261113-001152-town-blocked-survival-
recall_departure_ready (the viewing server's ~/hengbot-soak/n1-c/life-205/
incident-captures/, copied read-only into a scratch folder) and the character dump
the game wrote at the visit's row 3 ``periodic:character-dump`` (life-205/user/
bot_play3.txt, written 00:12:02 when the service stopped; the equipment, level, HP and
AC match row 3's board).

The town-arrival checkpoint (``policy.pkl``), the 19 journal rows (the stop is row 18)
and the sidecar files the restored policy reads (base64), xz-compressed; the loadout
report is left out.

    python tests/extract_n1c_205_food_devices_1113_fixture.py <capture dir> <dump file>
"""
import base64
import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-205-food-devices-1113"
ROWS = 19
LEFT_OUT = {"_loadout_report_path"}
PRESET = 9 | lzma.PRESET_EXTREME


def main(capture: Path, dump: Path) -> None:
    visit = capture / "town-arrival"
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
    rows = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(True)
    (FIXTURE / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(rows[:ROWS]), preset=PRESET))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    files = {}
    for role, entry in manifest.items():
        if role in LEFT_OUT:
            manifest[role] = {**entry, "copied": False, "reason": "left-out"}
        elif entry.get("copied"):
            files[role] = base64.b64encode((visit / "sidecars" / role).read_bytes()).decode("ascii")
    (FIXTURE / "sidecars.json.xz").write_bytes(lzma.compress(json.dumps(
        {"manifest": manifest, "files": files}, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    (FIXTURE / "dump-after-row3.txt.xz").write_bytes(lzma.compress(dump.read_bytes(), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
