"""Freeze the n1-b life-299 death boards of 2026-11-03 01:26 (オークの洞窟19階).

Source: the automatic player-death capture of the viewing warrior n1-b
(build 476464048), copied read-only to
C:/hengband-backups/pdca/captures/hourly-0100-1103/n1-b/life-299/incident-captures/
20261103-012616-player-death/:

  snapshots/snapshots-current.jsonl.gz
      the player boards of turns 930959-931557: the sighted walk down the
      corridor (the remembered map of the cells the blind player later
      stands in), the ヴラスタ's first blinding bite (931209), the seven
      Cure Critical Wounds each re-blinded by the next bite (931209-931269)
      and the blind walk to the known up-stair (931280-931557);
  snapshots/snapshots-20261103-011228-f2454d.jsonl.gz
      the last skill-proficiency and Home knowledge rows of the life (turn
      855866; the current generation holds none);
  decision-tail.jsonl
      the recorded decision rows of the same turns;
  policy-state.json
      the remembered terrain of the floor at the death (blind from turn
      931209 on, the player memorised no cell after it).

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this
extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_me_staff_loops_1031 import knowledge, ring_rows
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0100-1103/n1-b/life-299/incident-captures")
CAPTURE = "20261103-012616-player-death"
EARLIER = "snapshots-20261103-011228-f2454d.jsonl.gz"
SPAN = (930959, 931557)
OUTPUT = Path(__file__).with_name("fixtures") / "death-n1b-299-1103.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1b-299", CAPTURE, (SPAN,), races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    earlier = ring_rows(ROOT / CAPTURE / "snapshots" / EARLIER)
    case["skill"] = knowledge(earlier, len(earlier), "skill_exp")
    case["home"] = knowledge(earlier, len(earlier), "home")
    state = json.loads((ROOT / CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    case["terrain"] = state["terrain"]
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]))


if __name__ == "__main__":
    main()
