"""Extract tests/fixtures/n1c-207-summoner-pingpong-1113/.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1c-207-summoner-pingpong-1113/ (n1-c life-207, Magic-Eater
Lv46, Glass castle 60F):

- ``boards.json.gz``: captures/20261113-233731-loop-detected: every board of state.jsonl
  (turns 4911564-4912033, one floor visit) and the decision rows of those turns, with the
  monster knowledge (lib/edit/MonraceDefinitions.jsonc) of every race on the boards.
- ``policy.pkl.xz``: incident-captures/20261113-233728-loop-detected/town-arrival/policy.pkl,
  the policy checkpoint of the town arrival before this dive (turn 4910863).

    python tests/extract_n1c_207_summoner_pingpong_1113_fixture.py
"""
import lzma
from pathlib import Path

import extract_yeek_exit_loops_1110_fixtures as _extract
from extract_n1c_183_stairs_explore_loop_1109_fixtures import GAME, lines
from hengbot.monrace_knowledge import load_monrace_knowledge

ROOT = Path("C:/hengband-backups/pdca/captures/n1c-207-summoner-pingpong-1113")
ARRIVAL = ROOT / "incident-20261113-233728" / "town-arrival" / "policy.pkl"
OUTPUT = Path(__file__).with_name("fixtures") / "n1c-207-summoner-pingpong-1113"


def main() -> None:
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    _extract.OUTPUT = OUTPUT
    _extract.write("boards",
                   [row for row in lines(ROOT / "state.jsonl.gz") if row.get("type") == "player_turn"],
                   lines(ROOT / "bot-decisions.jsonl.gz"), races)
    (OUTPUT / "policy.pkl.xz").write_bytes(
        lzma.compress(ARRIVAL.read_bytes(), preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
