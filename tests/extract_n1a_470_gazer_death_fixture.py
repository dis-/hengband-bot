"""Freeze the n1-a life-470 death boards of 2026-11-03 09:50 (イークの洞穴13階).

Source: the automatic player-death capture of the viewing warrior n1-a
(build 96a499308), copied read-only to
C:/hengband-backups/pdca/captures/hourly-0900-1103/n1-a/life-470/incident-captures/
20261103-095012-player-death/:

  snapshots/snapshots-current.jsonl.gz
      the player boards of turns 293167-293675: the arrival on 13F, the
      sleeping ゲイザー stepped around (293334), the カミカゼ・イーク fight and
      the awake ゲイザー's approach answered by the walking retreat
      (``status-threat:retreat``, 293657-293675) before the paralysis;
  decision-tail.jsonl
      the recorded decision rows of the same turns.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this
extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0900-1103/n1-a/life-470/incident-captures")
CAPTURE = "20261103-095012-player-death"
SPAN = (293167, 293675)
OUTPUT = Path(__file__).with_name("fixtures") / "death-n1a-470-1103.json.gz"


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("n1a-470", CAPTURE, (SPAN,), races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]))


if __name__ == "__main__":
    main()
