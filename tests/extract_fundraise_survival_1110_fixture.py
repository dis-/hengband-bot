"""Freeze the boards of two 2026-11-10 mining-set town stops (build c6e2443b2).

Sources (copied read-only from the viewing bots to
C:/hengband-backups/pdca/captures/stops-1110/):

  n1a-507  n1-a life-507 (Lv22 Zombie Warrior), capture
           20261110-084026-town-blocked-survival-teleport-ready: state lines
           67-70, the Alchemist page of turn 472006 before the detection buy,
           after it, after the recall buy, and the street board of 472014.
  n1b-364  n1-b life-364 (Lv7 Zombie Magic-Eater), capture
           20261110-102137-town-blocked-survival-recall-departure-ready:
           state line 0, the Magic shop page of turn 135195 (the second
           visit, after the first one bought the スリープ・モンスターの魔法棒 at
           turn 135009 with 1,262 gold), and the decision row of that buy.

The fixture is one gzip JSON object.  Only this extraction tool reads the
captures; the committed tests read the fixture.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/stops-1110")
N1A = ROOT / "n1-a/life-507/captures/20261110-084026-town-blocked-survival-teleport-ready"
N1B = ROOT / "n1-b/life-364/captures/20261110-102137-town-blocked-survival-recall-departure-ready"
OUTPUT = Path(__file__).with_name("fixtures") / "fundraise-survival-1110.json.gz"
DECISION_FIELDS = ("turn", "reason", "key", "fundraising", "procurement_requirements",
                   "shop_selector")


def rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def decisions(path: Path, keep) -> list[dict]:
    return [{field: row.get(field) for field in DECISION_FIELDS}
            for row in rows(path / "bot-decisions.jsonl.gz") if keep(row)]


def main() -> None:
    n1a = rows(N1A / "state.jsonl.gz")
    boards = n1a[67:71]
    assert [board["turn"] for board in boards] == [472006, 472006, 472006, 472014]
    n1b = rows(N1B / "state.jsonl.gz")[0]
    assert n1b["turn"] == 135195 and n1b["player"]["gold"] == 78
    fixture = {
        "n1a-507": {
            "boards": boards,
            "decisions": decisions(N1A, lambda row: 472006 <= row["turn"] <= 472451),
        },
        "n1b-364": {
            "board": n1b,
            "decisions": decisions(
                N1B, lambda row: row["turn"] == 135009 or row["reason"].startswith("town:blocked")),
        },
    }
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
