"""Freeze the n1-c life-099 boards of an avoided immobile summoner (12F).

Source: the automatic player-death capture of the viewing Magic-Eater n1-c
(build dc64cf14a), copied read-only to
C:/hengband-backups/pdca/captures/n1c-death-1102-0148/.  Its snapshot ring
generation snapshots-20261102-014521-1341a3 holds 迷宮12階 (floor (4, 12, 0)),
01:45:12-01:45:16: a never-moving summoner held at the choke (2,27)
(decisions 117-121, ``summoner:hold-choke``), then the immobile-summoner
owner took every decision of the visit (``explore:avoid-immobile-summoner``,
decisions 122-150) -- also beside a visible worm mass and a warg.  Frozen:
the player boards of turns 675787-676308 (decisions 99-150, from the arrival
on the floor) in the layout of extract_n1c_deaths_1101_fixtures.freeze.  Only this extraction tool reads
the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_n1c_deaths_1101_fixtures import freeze


ROOT = Path("C:/hengband-backups/pdca/captures/n1c-death-1102-0148")
CAPTURE = "20261102-014821-player-death"
RING = "snapshots-20261102-014521-1341a3.jsonl.gz"
SPAN = (675787, 676308)
FLOOR = (4, 12)  # the generation also carries boards of a 10F stream


def _on_floor(row) -> bool:
    return (row["floor"]["dungeon_id"], row["floor"]["level"]) == FLOOR


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    frozen = freeze("n1c-099-summoner", CAPTURE, (SPAN,), races, root=ROOT, ring=RING,
                    keep=_on_floor)
    output = frozen.with_name("summoner-avoid-narrow-1102.json.gz")
    frozen.replace(output)
    print(output, output.stat().st_size)


if __name__ == "__main__":
    main()
