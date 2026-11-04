"""Extract tests/fixtures/n1c-2f-1104/ from n1-c life-139's Angband 2F walk.

Source: a tail of the instance's state.jsonl fetched at 2026-11-04 23:00 (the
23:04 redeploy truncated the file).  Kept: the last board on the floor.

    PYTHONPATH="src;tests;." python tests/extract_n1c_2f_1104_fixture.py <state-tail.jsonl>
"""
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1c-2f-1104"


def main(source: str) -> None:
    board = None
    for line in Path(source).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("grid_map"):
            board = row
    OUTPUT.mkdir(exist_ok=True)
    payload = json.dumps(board, ensure_ascii=False, sort_keys=True).encode("utf-8")
    (OUTPUT / "board-2f.json.xz").write_bytes(lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main(sys.argv[1])
