"""Freeze the D57 combat boards of 2026-11-01 (#47, d57-me-combat-1101).

Sources: the automatic player-death captures of the viewing Magic-Eater n1-c
(build c326f0fd6), copied read-only to
C:/hengband-backups/pdca/captures/fix-n1c-deaths-1101/ (one row of ``CASES``
per frozen case):

  083  life-083 (Lv14, 迷宮12階, 06:48): sighted again after the cure,
       a ブラウン・キラービートル (race 236) beside it; the recorded answer was
       the absorbed Magic Missile, then confusion and death.  Ring boards of
       turns 1190759-1190789.
  084  life-084 (Lv12, 迷宮14階, 07:49): a 充血アイ's gaze blinded it again
       on the board right after each Cure Critical Wounds until none was
       left.  Ring boards of turns 1287774-1288008.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's (player boards,
skill and Home rows, the ``_me_staff_sequence`` record, the monster knowledge
and the recorded decision rows).  Only this extraction tool reads the
captures; the committed tests read the frozen fixtures alone.
"""

from __future__ import annotations

from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


CASES = {
    "083": ("life-083/incident-captures/20261101-064758-player-death",
            ((1190759, 1190789),)),
    "084": ("life-084/incident-captures/20261101-074922-player-death",
            ((1287774, 1288008),)),
}


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    for name, (capture, spans) in CASES.items():
        frozen = freeze(f"d57-me-combat-{name}", capture, spans, races)
        output = frozen.with_name(f"d57-me-combat-{name}-1101.json.gz")
        frozen.replace(output)
        print(output, output.stat().st_size)


if __name__ == "__main__":
    main()
