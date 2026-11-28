"""Extract tests/fixtures/n1a-545-spell-cell-1128.jsonl.xz (tests/test_n1a_545_spell_cell_1128_recorded.py).

Source: n1-a life-545 (Amberite Rogue CL42, Sorcery, HP 865; build bot-3061aa3b1) on hengband.net,
the incident capture ``incident-captures/20261128-195309-stuck-prompt`` (its
``snapshots/snapshots-current.jsonl.gz``) and the stop's control screen
(``captures/20261128-195312-stuck-prompt-realm-spell-sensed-t1-in-line-teleport-away/
control-at-stop.json.gz``), copied read-only to
C:/hengband-backups/pdca/captures/n1a-545-spell-cell-1128/.  The live bot decided ``mbe@32,110``
(``realm-spell:sensed-t1-in-line:teleport-away``) on the board 8259826 (Angband 90F, waiting for
recall) and stopped at the direction prompt (``stuck-prompt ... unowned direction``).

Kept: the latest ``spell_list`` record of each Sorcery book before FIRST, every record (boards
and lists) from FIRST to LAST, then one ``control_screen`` row: the stop's screen (the direction
prompt), xz-compressed.

    python tests/extract_n1a_545_spell_cell_1128_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1a-545-spell-cell-1128")
SOURCE = CAPTURE / "snapshots-current.jsonl.gz"
CONTROL = CAPTURE / "control-at-stop.json.gz"
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-spell-cell-1128.jsonl.xz"
FIRST, LAST = 8259778, 8259826
SPELLS_PER_BOOK = 8


def main():
    earlier, rows = {}, []
    with gzip.open(SOURCE, "rt", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if row["turn"] < FIRST:
                if row.get("type") == "spell_list":
                    spells = row["spell_list"]["spells"]
                    earlier[spells[0]["spell_id"] // SPELLS_PER_BOOK] = row
            elif row["turn"] <= LAST:
                rows.append(row)
    control = json.loads(gzip.decompress(CONTROL.read_bytes()))
    kept = [*earlier.values(), *rows, {"type": "control_screen", "screen": control["screen"]}]
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in kept) + "\n"
    FIXTURE.write_bytes(lzma.compress(text.encode("utf-8"), preset=9))
    print(FIXTURE.name, len(kept), FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
