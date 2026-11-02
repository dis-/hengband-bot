"""Freeze the n1-c life-103 death boards of 2026-11-02 13:47 (城42階).

Source: the automatic player-death capture of the viewing Magic-Eater n1-c
(build 59230b90d), copied read-only to
C:/hengband-backups/pdca/captures/hourly-1400-1102/life-103/incident-captures/:

  life-103 (Lv36): 点『P』 teleported the player beside gargoyles, an
  アーチ=ヴァイル and 濃尾無双『岩本虎眼』 (turn 3831799).  Blinded at HP 388,
  then at HP 97/512 after a 291-HP round, it drank Cure Critical Wounds with
  Healing carried (3831859), read Teleport at HP 45 (3831864) and died to a
  シャドウ・デーモン's nether bolt after 点『P』 teleported it back.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this
extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/hourly-1400-1102/life-103/incident-captures")
CAPTURE = "20261102-134714-player-death"
SPAN = (3831825, 3831864)


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    frozen = freeze("n1c-103", CAPTURE, (SPAN,), races, root=ROOT)
    output = frozen.with_name("death-n1c-103-1102.json.gz")
    frozen.replace(output)
    print(output, output.stat().st_size)


if __name__ == "__main__":
    main()
