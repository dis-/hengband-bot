"""Extract tests/fixtures/stat-potions-home-1114/.

Source: n1-c life-207's town-arrival checkpoint 20261114-040255.297277795-turn5150183 (the
viewing server's ~/hengbot-soak/n1-c/life-207/jsonlog/town-arrival/, copied read-only to
C:/hengband-backups/pdca/captures/stat-potions-home-1114/n1-c/).  Its Home list holds the
Potions of Strength x2, Intelligence x2 and Wisdom x1 the bot shelved unknown.

The checkpoint (``policy.pkl``) and the visit's first journal rows, xz-compressed.

    python tests/extract_stat_potions_home_1114_fixture.py <town-arrival visit dir>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "stat-potions-home-1114"
ROWS = 5
PRESET = 9 | lzma.PRESET_EXTREME


def main(visit: Path) -> None:
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=PRESET))
    rows = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(True)
    (FIXTURE / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(rows[:ROWS]), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
