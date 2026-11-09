"""Extract tests/fixtures/stops-1109-town/.

Source: the town-arrival checkpoints of the viewing bots' town stops of
2026-11-08/09, as copied for the stops-1109 analysis (the incident captures
of the viewing server):

- ``a174``: n1-c life-174 2026-11-09 02:20 town:blocked:survival:recall_departure_ready.
- ``h497``: n1-a life-497 2026-11-09 03:58 town:blocked:unmet:home_candidate_resolved.
- ``e172``: n1-c life-172 2026-11-08 20:12 town:blocked:owner-retired-burst.
- ``d351``: n1-b life-351 2026-11-08 21:09 town:blocked:owner-retired-burst.
- ``g356``: n1-b life-356 2026-11-09 04:41 town:blocked:unmet:equipment_departure_ready.
- ``c349``: n1-b life-349 2026-11-08 20:02 town:blocked:owner-retired-burst.

Each keeps its pickled arrival policy, its journal cut to the rows the tests
replay, and its runtime sidecars with their manifest.

    python tests/extract_stops_1109_town_fixtures.py <a174> <h497> <e172> <d351> <g356> <c349>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "stops-1109-town"
ROWS = {"a174": 15, "h497": 38, "e172": 21, "d351": 130, "g356": 75, "c349": 1}


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
    for name, capture in zip(ROWS, sys.argv[1:7]):
        extract(name, Path(capture))


if __name__ == "__main__":
    main()
