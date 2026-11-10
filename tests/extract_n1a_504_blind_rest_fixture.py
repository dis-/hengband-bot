"""Freeze the n1-a life-504 boards of 2026-11-10 (鉄獄24階, random quest 41).

Source: the automatic player-death capture of the viewing warrior n1-a, copied
read-only to
C:/hengband-backups/pdca/captures/n1a-504-death-1110/incident/20261110-011720-player-death/
(the analysis is REPORT.txt beside it): the live ring generation's boards of
turns 877017-877691 (the arrival on the quest floor: the light hounds' flash
breaths and the thirteen cures), 880383-880451 (the last Healing) and
895901-897259 (the gas-trap blindness, the blind walk into the TY_CURSE trap
and the death), the remembered terrain of the policy state, and the recorded
decision rows (no Home row is in the live generation; the skill row is
its first one, see main).  The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.
Only this extraction tool reads the capture; the committed test reads the
fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import ring_rows
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/n1a-504-death-1110/incident")
CAPTURE = "20261110-011720-player-death"
SPANS = ((877017, 877691), (880383, 880451), (895901, 897259))
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-504-blind-1110.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1a-504", CAPTURE, SPANS, races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    state = json.loads((ROOT / CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    case["terrain"] = state["terrain"]
    if case["skill"] is None:
        # The live generation holds no skill row before the first span; its
        # first one is at turn 877589, inside it: the weapon and riding
        # skills, which the replay's melee reads.
        rows = ring_rows(ROOT / CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
        case["skill"] = next(row for row in rows if row["type"] == "knowledge"
                             and row["knowledge"]["category"] == "skill_exp")
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]), bool(case["skill"]), bool(case["home"]))


if __name__ == "__main__":
    main()
