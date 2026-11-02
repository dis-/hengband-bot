"""Freeze the n1-a life-466 death boards of 2026-11-03 02:31 (オークの洞窟14階).

Source: the automatic player-death capture of the viewing warrior n1-a
(build 38c599427), copied read-only to
C:/hengband-backups/pdca/captures/hourly-0200-1103/n1-a/life-466/incident-captures/
20261103-023107-player-death/:

  snapshots/snapshots-current.jsonl.gz
      the player boards of turns 3189880-3191559: the sighted fight with a
      腐った死体, the ヴラスタ's first blinding bite (3189929), the ten Cure
      Critical Wounds and the Healing each re-blinded by the next bite, the
      blind return walk to the known up-stair and the emergency ladder's
      walk and rests to the death (HP 23);
  decision-tail.jsonl
      the recorded decision rows of the same turns;
  policy-state.json
      the remembered terrain of the floor at the death.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's (its skill and
Home knowledge rows are the current generation's).  Only this extraction tool
reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0200-1103/n1-a/life-466/incident-captures")
CAPTURE = "20261103-023107-player-death"
SPAN = (3189880, 3191559)
OUTPUT = Path(__file__).with_name("fixtures") / "death-n1a-466-1103.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1a-466", CAPTURE, (SPAN,), races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    state = json.loads((ROOT / CAPTURE / "policy-state.json").read_text(encoding="utf-8"))
    case["terrain"] = state["terrain"]
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]))


if __name__ == "__main__":
    main()
