"""Extract tests/fixtures/town-stops-1104/ for test_town_stops_1104_recorded.

Source: C:/hengband-backups/pdca/captures/stops-1104-morning (builds
bot-2d4b7645d / bot-b044fd30f).  Each case keeps a capture's town-arrival
checkpoint (policy.pkl), the character calibration beside it and the journal
rows up to the stop's decision, recompressed with xz.

    python tests/extract_town_stops_1104_fixtures.py <captures/stops-1104-morning> [case ...]
"""
import gzip
import json
import lzma
import re
import sys
import zlib
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1104"
# Case name -> (instance/life, incident capture, journal rows kept).
CASES = {
    "merged-take": ("n1-a/life-475", "20261104-015340-town-blocked-survival-identify_staff_ready", 16),
    "stale-requests": ("n1-a/life-476", "20261104-025103-town-blocked-survival-identify_staff_ready", 2),
    "reserved-ring": ("n1-a/life-476", "20261104-023028-town-blocked-shop-required-operation-uncomposable", 9),
    "identification-wait": ("n1-a/life-476", "20261104-043627-departure-unsatisfiable", 20),
    "kit-latch": ("n1-b/life-306", "20261104-003239-town-blocked-owner-retired-burst", 28),
    "gold-pile": ("n1-c/life-123", "20261104-043315-town-blocked-owner-retired-burst", 51),
    "pack-identify": ("n1-a/life-476", "20261104-030834-town-blocked-survival-recall_departure_ready", 45),
    "worn-average": ("n1-b/life-307", "20261104-033207-town-blocked-pack-full-no-room", 35),
    # From the capture set beside it (bots bot-6925e7e43 / bot-a50ef8fcc).
    "ability-gap": ("../stops-1104-0750/n1-a/life-476", "20261104-072412-town-blocked-survival-depth_abilities", 12),
    "home-kit-bound": ("../stops-1104-0750/n1-a/life-476", "20261104-072335-town-blocked-owner-retired-burst", 25),
    # The stops of the 11-04 day (builds after 014ddb7dd).
    "pack-unrelieved": ("../stops-1104-1330/n1-a/life-477", "20261104-081722-town-blocked-unmet-equipment_departure_ready", 27),
    "closed-transaction": ("../stops-1104-1330/n1-c/life-129", "20261104-131829-town-blocked-unmet-equipment_departure_ready", 22),
    "ability-suppression": ("../stops-1104-1330/n1-a/life-477", "20261104-095223-town-blocked-survival-depth_abilities", 27),
    "entry-spent": ("../stops-1104-1330/n1-a/life-477", "20261104-085436-town-blocked-shop-required-operation-uncomposable", 66),
    "staff-need-room": ("../stops-1104-1330/n1-b/life-308", "20261104-131438-town-blocked-survival-identify_staff_ready", 22),
    # The sensed rings of n1-c life-130 (bot-28e3790a6).
    "ring-departure": ("../carry-gear-1104/n1-c/life-130", "jsonlog/town-arrival/20261104-152713.007536043-turn1861337", 35),
    "worn-ring": ("../worn-ring-1104/n1-c/life-130", "20261104-153933-town-blocked-survival-inventory_weight_ready", 3),
}
CALIBRATION = "_character_calibration_path"
# The small runtime files a replay of the visit's equipment work reads, for the
# cases of this set (stops-1104-1330).
RUNTIME_FILES = ("_confirmed_loadout_path", "_town_visit_purchase_path",
                 "_overweight_surplus_ledger_path", "_unseen_attack_path",
                 "_breeder_floor_record_path", "_exploration_ledger.path")
DUMP = "_character_dump_path"


def last_character_response(snapshots: Path, accept=lambda _line: True) -> bytes:
    """The ring's last C response (multi-member gzip tail from its first header)."""
    data = snapshots.read_bytes()
    data = data[data.find(b"\x1f\x8b\x08"):]
    found = b""
    while data:
        member = zlib.decompressobj(31)
        try:
            lines = member.decompress(data).split(b"\n")
        except zlib.error:
            following = data.find(b"\x1f\x8b\x08", 1)
            data = data[following:] if following >= 0 else b""
            continue
        data = member.unused_data
        found = next((line for line in reversed(lines)
                      if b'"stat_modifiers"' in line and accept(line)), found)
    return found


def response_of_dump(snapshots: Path, dump: bytes) -> bytes:
    """The last C response of the whole ring with the dump's maximum HP and gold.

    worn-ring: the arrival's dump is older than the visit's first C response.
    """
    text = dump.decode("euc-jp", errors="replace")
    max_hp = re.search(r"ＨＰ\s+\d+/\s*(\d+)", text)[1]
    gold = re.search(r"所持金\s+(\d+)", text)[1]

    def accept(line):
        player = json.loads(line)["player"]
        return str(player["max_hp"]) == max_hp and str(player["gold"]) == gold
    for path in sorted(snapshots.glob("*.jsonl.gz"), reverse=True):
        found = last_character_response(path, accept)
        if found:
            return found
    raise SystemExit(f"no C response of the dump in {snapshots}")


def main() -> None:
    root = Path(sys.argv[1])
    preset = 9 | lzma.PRESET_EXTREME
    for name, (life, capture, rows) in CASES.items():
        if len(sys.argv) > 2 and name not in sys.argv[2:]:
            continue
        visit = (root / life / capture if capture.startswith("jsonlog/")
                 else root / life / "incident-captures" / capture / "town-arrival")
        target = FIXTURES / name
        target.mkdir(parents=True, exist_ok=True)
        (target / "policy.pkl.xz").write_bytes(
            lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
        journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes())
        kept = b"".join(journal.splitlines(keepends=True)[:rows])
        (target / "journal.jsonl.xz").write_bytes(lzma.compress(kept, preset=preset))
        (target / "calibration.json").write_bytes((visit / "sidecars" / CALIBRATION).read_bytes())
        if "stops-1104-1330" in life:
            for role in RUNTIME_FILES:
                source = visit / "sidecars" / role
                if source.is_file():
                    (target / "runtime").mkdir(exist_ok=True)
                    (target / "runtime" / role).write_bytes(source.read_bytes())
        if name in {"worn-average", "ability-gap", "worn-ring"}:
            # The dump the arrival read, and the C response that goes with it.
            (target / "dump.txt.xz").write_bytes(
                lzma.compress((visit / "sidecars" / DUMP).read_bytes(), preset=preset))
            snapshots = visit.parent / "snapshots"
            response = (response_of_dump(snapshots, (visit / "sidecars" / DUMP).read_bytes())
                        if name == "worn-ring"
                        else last_character_response(snapshots / "snapshots-current.jsonl.gz"))
            (target / "character.json.xz").write_bytes(lzma.compress(response, preset=preset))


if __name__ == "__main__":
    main()
