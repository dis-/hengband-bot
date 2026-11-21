"""Extract tests/fixtures/n1c-219-death-1122.pkl.xz.

Source: n1-c life-219 (Zombie Magic-Eater Lv40, max HP 916), died on Angband 80F at 2026-11-22
05:56:13 (killed by 混沌, decision 14444, turn 2751732), copied read-only from the viewing
server's ``~/hengbot-soak/n1-c/life-219``:

* ``incident-captures/20261122-055613-player-death/town-arrival/policy.pkl``: the policy
  checkpoint taken before the last town visit (05:54:32, turn 2744144); its displayed lists
  hold the absorbed 光 (8 of 37 charges, 95%), テレポート and *破壊* (9 of 9, 90%);
* ``state.jsonl``: the boards (``type`` ``player_turn``) of turns
  2749569 (decision 14051, the first dark-room light of the floor: ``mAi``, which woke a ゲイザー
  and a 古代レッド・ドラゴン),
  2751620 (decision 14424, the Recall countdown: the board still shows the rock the absorbed
  mapping of decision 14419 drew west of the player),
  2751647 (decision 14428, twelve 混沌 in view, HP 766/916: ``qd`` ``emergency:heal``),
  2751654 (decision 14429, HP 600: ``rg`` ``emergency:teleport``),
  2751669 (decision 14431, after the landing at (37,17): ``mAi`` ``me-power:dark-room:lite-area``,
  whose next board says 「白い光が辺りを覆った。」「『マダム・デビ』が目を覚ました。」);
* the decision log rows of those boards (``decisions``: key and reason).

Kept as one xz-compressed pickle: ``checkpoint`` (bytes), ``boards`` ({turn: board dict}) and
``decisions`` ({turn: (key, reason)}).

    python tests/extract_n1c_219_death_1122_fixture.py <policy.pkl> <state.jsonl> <bot-decisions.jsonl>
"""
import json
import lzma
import pickle
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-219-death-1122.pkl.xz"
TURNS = (2749569, 2751620, 2751647, 2751654, 2751669)


def main(checkpoint_path: str, state_path: str, decisions_path: str) -> None:
    boards = {}
    with open(state_path, encoding="utf-8") as stream:
        for line in stream:
            raw = json.loads(line)
            if raw.get("type") == "player_turn" and raw.get("turn") in TURNS:
                boards[raw["turn"]] = raw  # the last board of a turn is the decision's
    decisions = {}
    with open(decisions_path, encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("turn") in TURNS:
                decisions[row["turn"]] = (row["key"], row["reason"])
    assert set(boards) == set(TURNS) == set(decisions), (sorted(boards), sorted(decisions))
    case = {"checkpoint": Path(checkpoint_path).read_bytes(), "boards": boards,
            "decisions": decisions}
    FIXTURE.write_bytes(lzma.compress(pickle.dumps(case), preset=9 | lzma.PRESET_EXTREME))
    print(FIXTURE.stat().st_size)


if __name__ == "__main__":
    main(*sys.argv[1:4])
