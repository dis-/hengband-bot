"""Freeze the town boards of two 2026-11-03 town stops (build 96a499308).

Sources: the automatic incident captures of the viewing warriors, copied
read-only to C:/hengband-backups/pdca/captures/hourly-0900-1103/:

  n1b-302  n1-b life-302 (Lv30, 09:48): the town visit after
           ``fundraise:ascend`` (turns 1376212-1376559) up to
           town:blocked:survival:cure_critical_ready.
  n1a-469  n1-a life-469 (09:02): the Home scan after the nine スピードの薬
           were taken (turns 773691-773711) up to
           town:blocked:unmet:home_candidate_resolved.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this
extraction tool reads the captures; the committed tests read the fixtures.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-0900-1103")
CASES = {
    "n1b-302": ("n1-b/life-302/incident-captures/"
                "20261103-094840-town-blocked-survival-cure_critical_ready",
                (1376212, 1376559)),
    "n1a-469": ("n1-a/life-469/incident-captures/"
                "20261103-090156-town-blocked-unmet-home_candidate_resolved",
                (773691, 773711)),
}


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    for name, (capture, span) in CASES.items():
        frozen = freeze(name, capture, (span,), races, root=ROOT)
        with gzip.open(frozen, "rt", encoding="utf-8") as stream:
            case = json.load(stream)
        frozen.unlink()
        output = Path(__file__).with_name("fixtures") / f"town-uncomposable-{name}-1103.json.gz"
        with gzip.open(output, "wt", encoding="utf-8", newline="\n") as stream:
            json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
        print(output, output.stat().st_size, len(case["boards"]), bool(case["home"]))


if __name__ == "__main__":
    main()
