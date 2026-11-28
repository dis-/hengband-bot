"""Extract tests/fixtures/n1a-545-buy-deadline-1128/ (tests/test_n1a_545_buy_deadline_1128_recorded.py).

Source: n1-a life-545 (Amberite Rogue, Sorcery), the incident capture
``incident-captures/20261128-170029-town-blocked-stage-deadline-buy`` copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1a-545-buy-deadline-1128/:

  town-arrival/           the arrival of 2026-11-28 16:59:47 (turn 7993175, build b81760a38),
                          every journal row up to the town:blocked:stage-deadline:buy stop

Kept: every journal row (the loadout report left out, as the other town-arrival fixtures).

    python tests/extract_n1a_545_buy_deadline_1128_fixture.py
"""
import gzip
from pathlib import Path

from support.town_arrival_fixture import extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1a-545-buy-deadline-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-buy-deadline-1128"


def main():
    rows = len(gzip.decompress((ROOT / "town-arrival" / "journal.jsonl.gz").read_bytes()).splitlines())
    extract(ROOT / "town-arrival", FIXTURE, rows, frozenset({"_loadout_report_path"}))
    print(rows, sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
