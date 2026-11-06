"""Freeze the n1-b life-292 boards of 2026-11-02 (Castle 18F) for the summoner shots.

Source: the viewing Magic-Eater n1-b life-292, copied read-only to
C:/hengband-backups/pdca/captures/viewing-incidents-20261102/n1-b/life-292/
incident-captures/20261102-084321-town-blocked-unmet-home_pending_item_clear/:
the boards of turns 1376393-1376494 of its fight on 城18階.  At turn 1376483
(HP 181/471) the decision was summoner:ranged-kill ``fu*t5``, and the next
board (HP 165) drank the healing potion (item:heal ``qd``).  The frozen layout
is extract_n1c_deaths_1101_fixtures.freeze's.  Only this extraction tool reads
the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/viewing-incidents-20261102/n1-b/life-292/"
            "incident-captures")
CAPTURE = "20261102-084321-town-blocked-unmet-home_pending_item_clear"
SPAN = (1376393, 1376494)
OUTPUT = Path(__file__).with_name("fixtures") / "n1b-292-summoner-after-survival-1102.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1b-292", CAPTURE, (SPAN,), races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]), bool(case["skill"]), bool(case["home"]))


if __name__ == "__main__":
    main()
