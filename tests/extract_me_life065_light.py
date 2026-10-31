"""Extract the n1-c life-065 Outpost boards of the Q2 Light-scroll block (2026-10-31).

Source: a read-only copy of hengbot-soak/n1-c/life-065/state.jsonl from the
viewing server (rows 0-72 are the Outpost visit before the 18:41 dive; the
character, Lv27, carried no Scroll of Light, and fixedquest readiness held
Q2 on required_scrolls.light 0/6).  Rows 27 (beside the Alchemist) and 28
(its observed page, Scrolls of Light at letter 'o') are kept as recorded.

Usage: python tests/extract_me_life065_light.py <state.jsonl copy>
"""
import gzip
import json
import sys
from pathlib import Path

ROWS = (27, 28)
OUT = Path(__file__).with_name("fixtures") / "me-light-waiver-life065-20261031.json.gz"


def main(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    boards = {str(index): json.loads(lines[index]) for index in ROWS}
    case = {"source": "n1-c life-065 state.jsonl rows 27-28 (turn 4833381)", "boards": boards}
    OUT.write_bytes(gzip.compress(json.dumps(case, ensure_ascii=False).encode("utf-8"), mtime=0))
    print(OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1])
