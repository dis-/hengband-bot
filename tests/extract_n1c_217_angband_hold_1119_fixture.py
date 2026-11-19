"""Extract tests/fixtures/n1c-217-angband-hold-1119/.

Source: n1-c life-217's town-arrival checkpoint of 2026-11-19 11:08:35 (turn 4,397,193; Magic-Eater
Lv41, Angband's recall landing 80, the Castle's 64), copied read-only from the viewing server's
~/hengbot-soak/n1-c/life-217/jsonlog/town-arrival/20261119-110835.171493298-turn4397193 into the
worktree's untracked .scratch/l217/.  Only the first journal row (the arrival board) is kept: the
test reads the destination decided on that board, not the visit.

    PYTHONPATH="src;tests" python tests/extract_n1c_217_angband_hold_1119_fixture.py
"""
from pathlib import Path

from support.town_arrival_fixture import extract

VISIT = (Path(__file__).resolve().parents[1] / ".scratch" / "l217"
         / "20261119-110835.171493298-turn4397193")
TARGET = Path(__file__).with_name("fixtures") / "n1c-217-angband-hold-1119"


def main() -> None:
    extract(VISIT, TARGET, 1, frozenset({"_loadout_report_path"}))


if __name__ == "__main__":
    main()
