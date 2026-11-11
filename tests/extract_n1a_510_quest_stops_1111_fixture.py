"""Extract tests/fixtures/n1a-510-quest-stops-1111/<stop>/.

Source: the incident captures of n1-a lives 509 and 510 (build bot-69967a2e2,
2026-11-11), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1a-509-510-1111/:

  q34      life-510 11:04 quest:blocked:fixed-target-not-visible (Q34).
  q2-1136  life-510 11:36 quest:blocked:q2-tower-recharge.
  death-509  life-509 11:03 player-death on Q18.

Each stop keeps its town-arrival checkpoint (``policy.pkl``), the journal, the
sidecar files the restored policy reads (base64) and, for the two floor stops,
``floor.jsonl`` -- the quest floor's recorded boards from the snapshot ring (the
journal holds town boards only).  All xz-compressed.

    python tests/extract_n1a_510_quest_stops_1111_fixture.py
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-509-510-1111")
FIXTURES = Path(__file__).with_name("fixtures") / "n1a-510-quest-stops-1111"
STOPS = {
    "q34": (ROOT / "life-510/incident-captures/20261111-110421-quest-blocked-fixed-target-not-visible", 34),
    "q2-1136": (ROOT / "life-510/incident-captures/20261111-113651-quest-blocked-q2-tower-recharge", None),
    "death-509": (ROOT / "life-509/incident-captures/20261111-110355-player-death", 18),
}
LEFT_OUT = {"_loadout_report_path"}
PRESET = 9 | lzma.PRESET_EXTREME


def main() -> None:
    for name, (capture, quest) in STOPS.items():
        visit = capture / "town-arrival"
        target = FIXTURES / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "policy.pkl.xz").write_bytes(
            lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
        (target / "journal.jsonl.xz").write_bytes(
            lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=PRESET))
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
        if quest is not None:
            rows = []
            with gzip.open(capture / "snapshots/snapshots-current.jsonl.gz", "rt", encoding="utf-8") as stream:
                for line in stream:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get("type") in {"player_turn", "knowledge"}:
                        rows.append(line)
            start = next(i for i, line in enumerate(rows)
                         if (json.loads(line).get("floor") or {}).get("quest_id") == quest)
            (target / "floor.jsonl.xz").write_bytes(lzma.compress(
                ("\n".join(rows[start:]) + "\n").encode("utf-8"), preset=PRESET))
        print(name, {path.name: path.stat().st_size for path in target.iterdir()})


if __name__ == "__main__":
    main()
