"""Extract tests/fixtures/n1c-205-recall-contradiction-1113/.

Source: the incident capture of n1-c life-205's
town:blocked:recall-readiness-contradiction stop, 2026-11-13 06:31:44, build
bot-784d60f71 (copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-205-recall-contradiction-1113/):
journal rows 0-54 (the canceller's row is 50, the stop row 54).  The loadout
report (an append-only log the policy only writes) is left out.

    PYTHONPATH="src;tests" python tests/extract_n1c_205_recall_contradiction_1113_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = Path("C:/hengband-backups/pdca/captures/n1c-205-recall-contradiction-1113/incident-captures/"
             "20261113-063144-town-blocked-recall-readiness-contradiction/town-arrival")
TARGET = Path(__file__).with_name("fixtures") / "n1c-205-recall-contradiction-1113"


if __name__ == "__main__":
    extract(VISIT, TARGET, 55, frozenset({"_loadout_report_path"}))
    print(sorted(path.name for path in TARGET.iterdir()))
