"""Extract tests/fixtures/n1c-214-recall-contradiction-1116/.

Source: the incident capture of n1-c life-214's
town:blocked:recall-readiness-contradiction stop, 2026-11-16 06:26:13, build
bot-8bb5c2fd3 (copied read-only from the viewing server's
~/hengbot-soak/n1-c/life-214/incident-captures/20261116-062611-town-blocked-recall-readiness-contradiction
to C:/hengband-backups/pdca/captures/n1c-214-recall-contradiction-1116/):
journal rows 0-43 (the recall read is row 33, the canceller's row 43).  The
loadout report (an append-only log the policy only writes) is left out.

    PYTHONPATH="src;tests" python tests/extract_n1c_214_recall_contradiction_1116_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1c-214-recall-contradiction-1116/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1c-214-recall-contradiction-1116"


if __name__ == "__main__":
    extract(VISIT, TARGET, 44, frozenset({"_loadout_report_path"}))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
