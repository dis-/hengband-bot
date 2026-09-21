"""Freeze the terminal organization-stall board from complete gzip members."""

import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "incident-captures"
    / "20260921-144642-town-blocked-owner-retired"
    / "snapshots"
    / "snapshots-current.jsonl.gz"
)
TARGET = ROOT / "tests" / "fixtures" / "organization-blocks-departure.jsonl.gz"
TARGET_TURN = 4281290


def main() -> None:
    compressed = SOURCE.read_bytes()
    signature = b"\x1f\x8b\x08"
    offsets: list[int] = []
    cursor = 0
    while (offset := compressed.find(signature, cursor)) >= 0:
        offsets.append(offset)
        cursor = offset + 1

    matches: list[dict] = []
    last_home: dict | None = None
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < len(offsets) else len(compressed)
        try:
            member = gzip.decompress(compressed[offset:end]).decode("utf-8")
        except (EOFError, gzip.BadGzipFile, UnicodeDecodeError):
            continue
        for line in member.splitlines():
            row = json.loads(line)
            if (row.get("store") or {}).get("store_type") == 7:
                last_home = row
            if row.get("turn") == TARGET_TURN and row.get("store") is None:
                matches.append(row)

    if len(matches) != 1 or last_home is None:
        raise RuntimeError(
            f"expected one terminal board and a Home board, found {len(matches)}, "
            f"home={last_home is not None}"
        )
    payload = "".join(
        json.dumps(row, ensure_ascii=False) + "\n"
        for row in (last_home, matches[0])
    ).encode("utf-8")
    TARGET.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))


if __name__ == "__main__":
    main()
