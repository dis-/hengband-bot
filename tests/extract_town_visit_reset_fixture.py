"""Extract tests/fixtures/town-visit-reset-20261103/.

Four town-arrival checkpoints of the 2026-11-03 viewing bots (build
bot-00d3a3726), each with the first rows of its visit journal, recompressed
with xz.  Their arrivals span what structure stage 3-2's rest moves into the
town visit:

* n1a-1232: n1-a life-472 12:32:02 departure-unsatisfiable: arrives holding a
  last buy, a last sale and a town-order operation from the previous visit;
  a pack with spare weapons and a Home page.
* n1a-1205: n1-a life-472 12:05:01 town-blocked-unmet: a Home deposit first.
* n1b-1158: n1-b life-302 11:58:09 loop-detected: the first store is a purchase.
* n1b-1203: n1-b life-302 12:03:39 town-blocked-survival: Home binds a
  catalogue shortage first.

    python tests/extract_town_visit_reset_fixture.py <captures-root>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "town-visit-reset-20261103"
SOURCES = {
    # name: (capture below the root, journal rows kept)
    "n1a-1232": ("viewing-incidents-20261103/n1-a/life-472/incident-captures/"
                 "20261103-123202-departure-unsatisfiable", 6),
    "n1a-1205": ("viewing-incidents-20261103/n1-a/life-472/incident-captures/"
                 "20261103-120501-town-blocked-unmet-home_candidate_resolved", 5),
    "n1b-1158": ("hourly-1100-1103/n1-b/life-302/incident-captures/"
                 "20261103-115809-loop-detected", 6),
    "n1b-1203": ("hourly-1100-1103/n1-b/life-302/incident-captures/"
                 "20261103-120339-town-blocked-survival-remove_curse_ready", 3),
}


def main() -> None:
    root = Path(sys.argv[1])
    preset = 9 | lzma.PRESET_EXTREME
    for name, (capture, rows) in SOURCES.items():
        visit = root / capture / "town-arrival"
        target = FIXTURE / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "policy.pkl.xz").write_bytes(
            lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
        journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes())
        kept = b"".join(journal.splitlines(keepends=True)[:rows])
        (target / "journal.jsonl.xz").write_bytes(lzma.compress(kept, preset=preset))


if __name__ == "__main__":
    main()
