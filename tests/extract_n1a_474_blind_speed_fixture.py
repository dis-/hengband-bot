"""Freeze the n1-a life-474 death boards of 2026-11-03 21:39 (鉄獄49階).

Source: the automatic player-death capture of the viewing warrior n1-a, copied
read-only to C:/hengband-backups/pdca/captures/stops-1103-night/n1-a/life-474/
incident-captures/20261103-213934-player-death/:

  snapshots/snapshots-current.jsonl.gz
      the explore steps at full HP (774) and the board of turn 2312011: 何か's
      darkness storm, HP 505, blind;
  decision-tail.jsonl
      the recorded decision rows of the same turns (item:cure-critical, ``qb``).

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this
extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/stops-1103-night/n1-a/life-474/incident-captures")
CAPTURE = "20261103-213934-player-death"
SPAN = (2311966, 2312011)
OUTPUT = Path(__file__).with_name("fixtures") / "death-n1a-474-1103.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1a-474", CAPTURE, (SPAN,), races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]))


if __name__ == "__main__":
    main()
