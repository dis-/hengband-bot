"""Freeze the n1-c life-169 stop (2026-11-08 13:43, Lv31, the Zul trip's inn walk).

Source: the viewing bot's ~/hengbot-soak/n1-c/life-169/incident-captures (copied with
its town-arrival checkpoint; pass the directory holding life-169/).

* inn (life-169, 13:43): the arrival checkpoint of 20261108-134314-town-blocked-owner-
  retired-burst (back in town at (31,150) from the Yeek cave fundraise) and its whole
  journal: the trip's walk to the inn one cell at a time, the native travel to the inn's
  side and the inn step '3md' that the CLI rewrote to the owner-retired-burst WAIT.
Only this tool reads the capture.

    python tests/extract_n1c_169_1108_fixtures.py <captures-root>
"""

from __future__ import annotations

from pathlib import Path
import sys

from extract_n1b_343_345_1108_fixtures import _checkpoint

FIXTURES = Path(__file__).with_name("fixtures") / "n1c-169-1108"
INN = "life-169/incident-captures/20261108-134314-town-blocked-owner-retired-burst"


def main(root: Path) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    _checkpoint(FIXTURES / "inn.tar.xz", root / INN, None)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
