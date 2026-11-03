"""Freeze the n1-a life-475 boards of 2026-11-04 02:25 (城49階).

Source: the automatic player-death capture of the viewing warrior n1-a, copied
read-only to C:/hengband-backups/pdca/captures/stops-1104-morning/n1-a/life-475/
incident-captures/20261104-022543-player-death/: the boards of turns
2038869-2039042, the landing of the second emergency teleport beside the
sleeping undead and the summoner:ranged-kill shots that followed.  The frozen
layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this extraction tool
reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/stops-1104-morning/n1-a/life-475/incident-captures")
CAPTURE = "20261104-022543-player-death"
SPAN = (2038869, 2039042)
OUTPUT = Path(__file__).with_name("fixtures") / "death-n1a-475-1104.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1a-475", CAPTURE, (SPAN,), races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]), bool(case["skill"]), bool(case["home"]))


if __name__ == "__main__":
    main()
