"""Extract tests/fixtures/relief-overweight-1107/.

Source: n1-a life-492 (viewing server, build 00c553cd8, 2026-11-07), the
town-arrival checkpoints of three incident captures:

- ``a1``: incident-captures/20261107-125924-town-blocked-owner-retired-burst
  (12:58:48 arrival; the sweep's flail take, decisions 10378-10389).
- ``a2``: incident-captures/20261107-123331-town-blocked-owner-retired-burst
  (12:32:44 arrival; the (トランプ)首切りソード take, decisions 1023-1078).
- ``b1``: incident-captures/20261107-123039-town-blocked-overweight-surplus-rebuy-loop
  (12:30:12 arrival; the overweight sales and the 鑑定の杖 take, 29654-29698).

Each keeps its pickled arrival policy, its journal cut to the rows the tests
replay, and its runtime sidecars with their manifest.

    python tests/extract_relief_overweight_1107_fixtures.py <a1-capture> <a2-capture> <b1-capture>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "relief-overweight-1107"
ROWS = {"a1": 100, "a2": 76, "b1": 59}


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
    for name, capture in zip(("a1", "a2", "b1"), sys.argv[1:4]):
        extract(name, Path(capture))


if __name__ == "__main__":
    main()
