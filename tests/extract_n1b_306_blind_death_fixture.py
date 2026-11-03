"""Freeze the n1-b life-306 death boards of 2026-11-04 01:54 (鉄獄19階).

Source: the automatic player-death capture of the viewing warrior n1-b,
copied read-only to
C:/hengband-backups/pdca/captures/stops-1104-morning/n1-b/life-306/incident-captures/
20261104-015401-player-death/: the boards of turns 4876566-4877039 (the walk
down from the Recall landing, the ヴラスタ's bites and the blind fight to the
death), the skill and Home knowledge rows of the ring's last generation that
has them, and the recorded decision rows.  The frozen layout is
extract_n1c_deaths_1101_fixtures.freeze's.  Only this extraction tool reads the
capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/stops-1104-morning/n1-b/life-306/incident-captures")
CAPTURE = "20261104-015401-player-death"
SPAN = (4876566, 4877039)
OUTPUT = Path(__file__).with_name("fixtures") / "death-n1b-306-1104.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1b-306", CAPTURE, (SPAN,), races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    state = json.loads((ROOT / CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    case["terrain"] = state["terrain"]
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]), bool(case["skill"]), bool(case["home"]))


if __name__ == "__main__":
    main()
