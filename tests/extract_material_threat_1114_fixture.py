"""Extract tests/fixtures/material-threat-1114.json.xz.

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-207-recall-churn-1114/: n1-c life-207 (Magic-Eater Lv46,
build bot-7c614b268) on ガラスの城 (Glass castle, dungeon 20) 60F, 2026-11-14.
``snap-current.jsonl.gz`` holds every response line of 04:21-04:31 and ``dec-tail4.jsonl.gz``
the decision rows.  Two Recalls of that window were read after a single emergency escape with
the trigger ``emergency-material-threat`` while no visible summoner could summon before the
player's next action (owner 2026-11-14 「当てはめる」):

* 04:29:05: emergency:teleport (decision 609), the landing board (610, game turn 5218920:
  ニーベルング族の王『アルベリヒ』 and 水の鬼 asleep at cdis 15), Recall (611);
* 04:31:06: emergency:teleport (1538), the landing board (1539, game turn 5228336: 混沌の王族 at
  cdis 20 and 腐敗ビホルダー at cdis 18), Recall (1541).

The tool keeps each landing board's response line and the decision rows from the escape to the
Recall, as one xz-compressed JSON.  No policy checkpoint of these dives was copied (the bot
restarted at 04:27 and the next town-arrival checkpoint was not taken).

    python tests/extract_material_threat_1114_fixture.py
"""
import gzip
import json
import lzma
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("C:/hengband-backups/pdca/captures/n1c-207-recall-churn-1114")
SNAPSHOTS = ROOT / "snap-current.jsonl.gz"
DECISIONS = ROOT / "dec-tail4.jsonl.gz"
OUTPUT = HERE / "fixtures" / "material-threat-1114.json.xz"
SINCE = "2026-11-14T04:28:30"  # after the 04:27 restart's first Recall
LANDINGS = {5218920: (609, 610, 611), 5228336: (1538, 1539, 1541)}
DECISION_FIELDS = ("decision_sequence", "time", "turn", "key", "reason")


def _jsonl(path):
    """The rows; the live generation may end in a member still being written."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                try:
                    yield line, json.loads(line)
                except ValueError:
                    continue  # a line the copy cut
    except (EOFError, zlib.error):
        return


def main() -> None:
    boards = {row["turn"]: line for line, row in _jsonl(SNAPSHOTS)
              if row.get("type") == "player_turn" and row.get("turn") in LANDINGS}
    wanted = {sequence for sequences in LANDINGS.values() for sequence in sequences}
    rows = {}
    for _line, row in _jsonl(DECISIONS):
        if row.get("time", "") >= SINCE and row.get("decision_sequence") in wanted:
            rows.setdefault(row["decision_sequence"], {field: row.get(field)
                                                       for field in DECISION_FIELDS})
    landings = []
    for turn, sequences in sorted(LANDINGS.items()):
        decided = [rows[sequence] for sequence in sequences]
        if decided[1]["turn"] != turn or decided[2]["reason"] != "return:recall":
            raise SystemExit(f"{turn}: unexpected rows {decided}")
        landings.append({"line": boards[turn], "decisions": decided})
    OUTPUT.write_bytes(lzma.compress(json.dumps({"source": ROOT.name, "landings": landings},
                                                ensure_ascii=False).encode("utf-8"),
                                     preset=9 | lzma.PRESET_EXTREME))
    print(OUTPUT, OUTPUT.stat().st_size, len(landings))


if __name__ == "__main__":
    main()
