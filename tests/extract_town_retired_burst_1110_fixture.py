"""Extract tests/fixtures/town-retired-burst-1110/<stop>/.

Source: the town:blocked:owner-retired-burst incident captures of 2026-11-10
(copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/town-retired-burst-1110/):

  n1a-508  n1-a life-508, build bot-90b1d07af, 21:05 (incident-210513):
           the Home withdrawal visit, journal rows 0-74 (the stop).
  n1a-508-2243  n1-a life-508 again, build bot-49436da51, 22:43
           (incident-224338): the next Home visit, journal rows 0-75 (the stop).
  n1a-508-0040  n1-a life-508 again, build bot-d91e4a4ec, 2026-11-11 00:40
           (incident-004001): the recall stock-out visit, journal rows 0-44
           (the end of the stock-out run the Home deposit caused).
  n1a-508-0320  n1-a life-508 again, build bot-cfc720d28, 2026-11-11 03:20
           (incident-032007): the *Identify* purchase visit, journal rows
           0-19 (town:blocked:survival:identify_staff_ready on the next).
  n1b-364  n1-b life-364, build bot-c6e2443b2, 10:18 (incident-101818):
           the walk to the Magic shop, journal rows 0-59 (the torch throw,
           the bookkeeping after it and the walk round the town wall).
  n1b-365  n1-b life-365, 2026-11-10 16:28 (incident 162843): the
           depth-gate waits whose third retirement made the burst, journal
           rows 0-16 (the stop).
  n1b-370  n1-b life-370, build bot-5639115f7, 2026-11-11 15:54 (incident
           155453): the walk across Zul to the Levitation shop, journal rows
           0-57 (the stop).
  n1c-195  n1-c life-195, build bot-609de4219, 2026-11-11 17:29 (incident
           172943): the Home identification-catalog takes, journal rows
           0-114 (the first idle step-off after the outside ``~9``).

Each stop keeps its town-arrival checkpoint (``policy.pkl``), the journal rows
named above and the sidecar files the restored policy reads (base64), all
xz-compressed.
The loadout report (an append-only log the policy only writes) is left out.

    python tests/extract_town_retired_burst_1110_fixture.py
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/town-retired-burst-1110")
FIXTURES = Path(__file__).with_name("fixtures") / "town-retired-burst-1110"
STOPS = {
    "n1a-508": (ROOT / "n1-a-life-508/incident-210513/town-arrival", 75),
    "n1a-508-2243": (ROOT / "n1-a-life-508/incident-224338/town-arrival", 76),
    "n1a-508-0040": (ROOT / "n1-a-life-508/incident-004001/town-arrival", 45),
    "n1a-508-0320": (ROOT / "n1-a-life-508/incident-032007/town-arrival", 20),
    "n1b-364": (ROOT / "n1-b-life-364/incident-101818/town-arrival", 60),
    "n1b-365": (ROOT / "n1-b-life-365/incident-162843/town-arrival", 17),
    "n1b-370": (ROOT / "n1-b-life-370/incident-155453/town-arrival", 58),
    "n1c-195": (ROOT / "n1-c-life-195/incident-172943/town-arrival", 115),
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
