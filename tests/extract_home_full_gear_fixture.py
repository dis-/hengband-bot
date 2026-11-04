"""Extract tests/fixtures/spare-gear-1104/<case>/ for test_home_full_gear_recorded.

Source: C:/hengband-backups/pdca/captures/home-full-1104/n1-c, the stops named
town:blocked:overweight-home-full-no-legal-relief.  Each case keeps a town-arrival
checkpoint, its whole journal and the character calibration, with xz.

    python tests/extract_home_full_gear_fixture.py <captures/home-full-1104/n1-c>
"""
import gzip
import lzma
import sys
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "spare-gear-1104"
CASES = {
    "home-full-stop": "life-130/incident-captures/20261104-204046-town-blocked-overweight-home-full-no-legal-relief",
    "home-full-2142": "life-134/incident-captures/20261104-214240-town-blocked-overweight-home-full-no-legal-relief",
    "home-full-2146": "life-134/incident-captures/20261104-214606-town-blocked-overweight-home-full-no-legal-relief",
}


def main() -> None:
    root = Path(sys.argv[1])
    preset = 9 | lzma.PRESET_EXTREME
    for name, capture in CASES.items():
        visit = root / capture / "town-arrival"
        target = FIXTURES / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "policy.pkl.xz").write_bytes(
            lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
        (target / "journal.jsonl.xz").write_bytes(
            lzma.compress(gzip.decompress((visit / "journal.jsonl.gz").read_bytes()), preset=preset))
        (target / "calibration.json").write_bytes(
            (visit / "sidecars" / "_character_calibration_path").read_bytes())


if __name__ == "__main__":
    main()
