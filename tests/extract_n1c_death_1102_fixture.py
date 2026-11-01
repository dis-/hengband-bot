"""Freeze the n1-c life-099 death boards of 2026-11-02 (n1c-death-1102).

Source: the automatic player-death capture of the viewing Magic-Eater n1-c
(build dc64cf14a), copied read-only to
C:/hengband-backups/pdca/captures/n1c-death-1102-0148/:

  life-099 (Lv23, クエスト31『柳じじい』, 01:48): every board of the quest
  floor, turns 691290 (entry) - 691735 (death).  The Speed potion of 691305
  ran out on 691537 with sasquatches and sabre-tooth tigers beside it and the
  second potion stayed in the pack; from 691606 (HP 199/310) the absorbed
  Teleport Away was aimed at one sasquatch after another, down to HP 18.

The frozen layout is extract_n1c_deaths_1101_fixtures.freeze's.  Only this
extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-death-1102-0148")
CAPTURE = "20261102-014821-player-death"
SPAN = (691290, 691735)


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    frozen = freeze("n1c-099", CAPTURE, (SPAN,), races, root=ROOT)
    output = frozen.with_name("death-n1c-099-1102.json.gz")
    frozen.replace(output)
    print(output, output.stat().st_size)


if __name__ == "__main__":
    main()
