"""Extract tests/fixtures/town-stops-1105/ for test_town_stops_1105_recorded.

Each case keeps a capture's town-arrival checkpoint, its sidecars and the
journal rows up to the pinned decision, as one xz tar.

    python tests/extract_town_stops_1105_fixtures.py <captures root> [case ...]

The root holds <instance>/life-NNN/incident-captures/<stamp>-<kind>/town-arrival
(copied from the viewing bots on 2026-11-05 and 06).
"""
import gzip
import io
from pathlib import Path
import sys
import tarfile

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1105"
# Case name -> (capture, journal rows kept).
CASES = {
    "rumor-walk": ("n1-b/life-314/incident-captures/20261105-134350-town-blocked-owner-retired-burst", 12),
    "town-changed": ("n1-c/life-145/incident-captures/20261105-231819-town-blocked-owner-retired-burst", 7),
    "own-home-route": ("n1-b/life-317/incident-captures/20261105-231901-town-blocked-owner-retired-burst", 72),
    "staff-swap": ("n1-a/life-487/incident-captures/20261105-191417-town-blocked-survival-identify_staff_ready", 16),
    "filed-take": ("n1-a/life-487/incident-captures/20261105-193019-town-blocked-unmet-home_candidate_resolved", 58),
    "entrance-walk": ("n1-a/life-487/incident-captures/20261105-133941-town-blocked-survival-cure_critical_ready", 62),
    "expedition": ("n1-a/life-486/incident-captures/20261105-114110-town-blocked-unmet-home_candidate_resolved", 56),
    "periodic-walk": ("n1b-319-1106/incident-captures/20261106-012252-stuck-prompt", 7),
    # Under C:/hengband-backups/pdca/captures/mining-oil-1106.
    "mining-identify": ("n1-b/life-315/incident-captures/20261105-135017-loop-detected", 45),
    "mining-oil-sale": ("n1-b/life-315/incident-captures/20261105-135047-town-blocked-survival-recall_departure_ready", 92),
    "q34-lantern-town": ("n1-c/life-141/incident-captures/20261105-054512-town-blocked-survival-recall_departure_ready", 18),
}


def add(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def extract(root: Path, case: str) -> None:
    capture, rows = CASES[case]
    visit = root / capture / "town-arrival"
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with tarfile.open(FIXTURES / f"{case}.tar.xz", "w:xz", preset=9) as tar:
        add(tar, "policy.pkl", (visit / "policy.pkl").read_bytes())
        add(tar, "sidecars.json", (visit / "sidecars.json").read_bytes())
        for path in sorted((visit / "sidecars").iterdir()):
            add(tar, f"sidecars/{path.name}", path.read_bytes())
        with gzip.open(visit / "journal.jsonl.gz", "rt", encoding="utf-8") as stream:
            kept = [line for _, line in zip(range(rows), stream)]
        add(tar, "journal.jsonl.gz", gzip.compress("".join(kept).encode("utf-8"), mtime=0))


if __name__ == "__main__":
    for name in sys.argv[2:] or CASES:
        extract(Path(sys.argv[1]), name)
