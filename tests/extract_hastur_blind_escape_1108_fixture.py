"""Extract the 2026-11-08 fixture of the blind teleport escape (threat_tiers.blind_teleport_key).

Source, read-only, the capture of n1-c life-171's death (Zombie Magic-Eater Lv50, 城65階,
2026-11-08 20:08, killed by 名状しがたきもの『ハスター』 after 皇帝『レイザーク』's darkness storm):

 * <keep-running>/state.jsonl: the player_turn boards of the second 65F visit, turns
   FIRST..LAST (decisions 20580-20590; 20589 is turn 4244017, 20590 is 4244027);
 * <player-death>/snapshots/snapshots-current.jsonl.gz: the last "knowledge" row with
   skill_exp before FIRST;
 * <player-death>/town-arrival/policy.pkl: the absorbed device lists the game last displayed
   (``_me_device_lists``: kind -> (turn, rows)), the lists the live policy held on these boards.

Output: tests/fixtures/hastur-blind-escape-n1c-171-1108.json.xz
({"skill": ..., "lists": {kind: [turn, rows]}, "boards": [...]}).

    python tests/extract_hastur_blind_escape_1108_fixture.py <capture directory>
"""
import gzip
import json
import lzma
import pathlib
import pickle
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "hastur-blind-escape-n1c-171-1108.json.xz"
FIRST, LAST = 4243941, 4244027


def main() -> None:
    capture = Path(sys.argv[1])
    boards = []
    with open(capture / "20261108-200759-keep-running" / "state.jsonl", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST:
                boards.append(row)
    death = capture / "20261108-200756-player-death"
    skill = None
    with gzip.open(death / "snapshots" / "snapshots-current.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("type") == "knowledge" and "skill_exp" in line and row["turn"] <= FIRST:
                skill = row
    # The checkpoint was pickled on Linux; its runtime paths are PosixPath.
    pathlib.PosixPath = pathlib.WindowsPath if sys.platform == "win32" else pathlib.PosixPath
    with open(death / "town-arrival" / "policy.pkl", "rb") as stream:
        state = pickle.load(stream)
    lists = {kind: [turn, list(rows)] for kind, (turn, rows) in state["_me_device_lists"].items()}
    FIXTURE.write_bytes(lzma.compress(
        json.dumps({"skill": skill, "lists": lists, "boards": boards}, ensure_ascii=False).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
