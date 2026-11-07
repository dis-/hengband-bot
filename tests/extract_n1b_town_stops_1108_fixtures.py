"""Extract tests/fixtures/n1b-town-stops-1108/.

Source: n1-b life-338 and life-339 (viewing server, 2026-11-07/08), the
town-arrival checkpoints of four incident captures:

- ``a``: life-338 incident-captures/20261107-195041-stuck-prompt
  (build 5aecae125; the armour smith's one-item chooser).
- ``b``: life-338 incident-captures/20261107-215223-town-blocked-owner-retired-burst
  (build 5d89656b3; the (トランプ)ブロード・スピア take and re-deposit).
- ``c``: life-338 incident-captures/20261107-173408-quest-blocked-me-staff
  (build 3b50eab56; the drunk near the Outpost inn).
- ``d``: life-339 incident-captures/20261108-023045-loop-detected
  (build 96533207e; the Alchemist without Word of Recall).

Each keeps its pickled arrival policy, its journal cut to the rows the tests
replay, and its runtime sidecars with their manifest.  ``armor-smith-one-item-
screen.json`` is the screen of life-338 captures/20261107-195042-stuck-prompt-
town-armor-smith-raise/control-at-stop.json.gz (blank rows dropped).

    python tests/extract_n1b_town_stops_1108_fixtures.py <a> <b> <c> <d>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "n1b-town-stops-1108"
ROWS = {"a": 30, "b": 20, "c": 258, "d": 76}


def extract(name: str, capture: Path) -> None:
    visit = capture / "town-arrival"
    target = OUTPUT / name
    target.mkdir(parents=True, exist_ok=True)
    preset = 9 | lzma.PRESET_EXTREME
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(journal[:ROWS[name]]), preset=preset))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    # Bytes as latin-1 text: the character dump is EUC-JP.
    sidecars = dict(manifest=manifest, files={
        role: (visit / "sidecars" / role).read_bytes().decode("latin-1")
        for role, entry in manifest.items() if entry.get("copied")})
    (target / "sidecars.json.xz").write_bytes(lzma.compress(
        json.dumps(sidecars, ensure_ascii=False).encode("utf-8"), preset=preset))
    for path in sorted(target.iterdir()):
        print(name, path.name, path.stat().st_size)


def main() -> None:
    for name, capture in zip(("a", "b", "c", "d"), sys.argv[1:5]):
        extract(name, Path(capture))


if __name__ == "__main__":
    main()
