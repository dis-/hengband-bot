"""Regenerate the immutable Stage-2b incident window byte-for-byte."""

from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "jsonlog/incident-20260913-town-pingpong-gold-burn/bot-state-fixed.jsonl"
TARGET = ROOT / "tests/fixtures/input-barrier-stage2b-rec74-96.jsonl"


def main() -> None:
    lines = SOURCE.read_bytes().splitlines(keepends=True)
    assert len(lines) >= 96
    TARGET.write_bytes(b"".join(lines[73:96]))


if __name__ == "__main__":
    main()
