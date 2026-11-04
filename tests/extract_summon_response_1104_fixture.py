"""Freeze the n1-a life-475 boards the summon response tests replay (2026-11-04, 城49階).

Source: the automatic player-death capture of the viewing warrior n1-a, copied
read-only to C:/hengband-backups/pdca/captures/stops-1104-morning/n1-a/life-475/
incident-captures/20261104-022543-player-death/.  Spans of the ring's newest generation:

 * the unseen demon summoner of 2027761-2027800 at (48,25);
 * the visible 悪魔崇拝者 of 2033705-2033737, a summoned monster beside the player;
 * the last fight, 2038849-2039200: from the board before the first summon to the death.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this extraction
tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/stops-1104-morning/n1-a/life-475/incident-captures")
CAPTURE = "20261104-022543-player-death"
SPANS = ((2027761, 2027800), (2033705, 2033737), (2038849, 2039200))
OUTPUT = Path(__file__).with_name("fixtures") / "summon-response-n1a-475-1104.json.gz"
# The ring holds no skill or home list before the first span: the same life's, frozen later.
LATER_KNOWLEDGE = OUTPUT.with_name("death-n1a-475-1104.json.gz")


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    frozen = freeze("summon-response-n1a-475", CAPTURE, SPANS, races, root=ROOT)
    with gzip.open(frozen, "rt", encoding="utf-8") as stream:
        case = json.load(stream)
    frozen.unlink()
    with gzip.open(LATER_KNOWLEDGE, "rt", encoding="utf-8") as stream:
        later = json.load(stream)
    case["skill"], case["home"] = later["skill"], later["home"]
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size, len(case["boards"]), bool(case["skill"]), bool(case["home"]))


if __name__ == "__main__":
    main()
