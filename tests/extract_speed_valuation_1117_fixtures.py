"""Extract tests/fixtures/speed-valuation-1117/: the optimizer inputs of three viewing bots.

Owner 2026-11-17 「装備最適化のスピードの評価を上げて。特にspeed+20までは生存に大きく寄与する」
(「時間あたりの打撃＋+20までを強く」).  Source: the town-arrival checkpoints of the
viewing server copied read-only on 2026-11-17 14:1x to
C:/hengband-backups/pdca/captures/speed-valuation-1117/<bot>/town-arrival/, with the
tail of each life's loadout-report.jsonl (the recorded choice, ``RECORDED``).

Each checkpoint is restored (tests/replay_town_arrival.py) and its journal rows are
decided and posted with their recorded keys until the policy's own equipment
optimization (policy_equipment._prepare_equipment_optimization) yields a loadout;
the arguments it passed to ``prepare_warrior_optimization`` are pickled (the
loadout-report path and the evaluator cache left out) and xz-compressed.  Run on
main 3a7d538a6 the four choices equal the recorded ones (VISITS).

DECLARED CONSTRUCTED (n1-c only): the 13:53:10 arrival of n1-c life-216 holds the
calibration of before a DEX drain (its visible stat key reads DEX 130, the board
-130) and no ~f skill read; the visit's own dump row has no dump file in the
capture.  The calibration's visible stat key is set to the board's and the
two-weapon skill 560 (shield 0) is the ~f value the 13:53:58 checkpoint of the same
character read on its first row.  The optimizer then answers the recorded choice
(melee 493.9, speed +2) exactly.

    python tests/extract_speed_valuation_1117_fixtures.py
    (PYTHONPATH: src, tests and the root)
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import json
import lzma
import pickle
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import hengbot.policy_equipment as policy_equipment
import hengbot.warrior_optimization as warrior_optimization
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import SIDECAR_DIRECTORY
from hengbot.warrior_optimization import load_character_calibration
from replay_town_arrival import adopt_calibration, decisions, restore

CAPTURES = Path("C:/hengband-backups/pdca/captures/speed-valuation-1117")
TARGET = Path(__file__).with_name("fixtures") / "speed-valuation-1117"
PRESET = 9 | lzma.PRESET_EXTREME
# fixture: (bot, checkpoint, ~f two-weapon skill to supply, first journal row to
# optimize after, the loadout report row of the same choice).  n1-a: after row 1
# (the visit's restore-combat-weapon posted).  n1-b's arrival board chooses the
# ★炎の鉄ゲタ set at -1 the report recorded at 14:11:13 (melee 254.0), and after its
# Home knowledge scan (row 7) the +7 set it recorded from 14:11:18 on (215.7): the
# two alternate.
VISITS = {
    "n1-a": ("n1-a", "20261117-141122.505835360-turn6489656", None, 1, "2026-11-17T14:11:23+09:00"),
    "n1-b-arrival": ("n1-b", "20261117-141154.712571745-turn4944494", None, 0,
                     "2026-11-17T14:11:13+09:00"),
    "n1-b": ("n1-b", "20261117-141154.712571745-turn4944494", None, 8, "2026-11-17T14:12:00+09:00"),
    "n1-c": ("n1-c", "20261117-135310.459220393-turn5378424", 560, 0, "2026-11-17T13:54:14+09:00"),
}
LEFT_OUT = frozenset({"loadout_report_path", "evaluator_cache"})


def capture(bot: str, visit_name: str, two_weapon_skill: int | None, first_row: int):
    visit = CAPTURES / bot / "town-arrival" / visit_name
    calls = []
    original = warrior_optimization.prepare_warrior_optimization

    def spy(snapshot, items, knowledge, **kwargs):
        result = original(snapshot, items, knowledge, **kwargs)
        kept = {name: value for name, value in kwargs.items() if name not in LEFT_OUT}
        calls.append(((snapshot, items, knowledge, kept), result))
        return result

    with TemporaryDirectory(prefix="speed-1117-extract-") as raw:
        scratch = Path(raw)
        policy = restore(visit, scratch)
        recorded_calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        adopt_calibration(policy, recorded_calibration, scratch)
        with patch.object(policy_equipment, "prepare_warrior_optimization", spy):
            for row, supply in decisions(policy, visit, scratch):
                board = supply()
                policy.choose_key(board)
                key = row["key"]
                if key:
                    policy.confirm_key_posted(key)
                    chain = policy.peek_staged_prompt_chain()
                    if chain is not None and staged_prompt_chain_matches(chain, key):
                        policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
                if not board.in_town or row["row"] < first_row:
                    continue
                if two_weapon_skill is not None:
                    # DECLARED CONSTRUCTED (module docstring).
                    calibration = replace(
                        load_character_calibration(recorded_calibration),
                        visible_stat_key=board.player.printed_stat_cur_key)
                    policy._character_calibration = calibration
                    policy._character_calibration_loaded = True
                    policy._validated_character_calibration = lambda _board, c=calibration: c
                    policy._skill_exp_cache = (
                        two_weapon_skill, 0, board.player.level, policy._town_visit_epoch)
                calls.clear()
                policy._equipment_optimization_signature = None
                policy._prepare_equipment_optimization(policy._with_cached_skill_exp(board))
                found = [call for call in calls
                         if call[1].result is not None and call[1].result.best is not None]
                if found:
                    return found[0][0]
    raise SystemExit(f"{bot}: no optimization in the visit")


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    recorded = {}
    for name, (bot, visit_name, skill, first_row, report_time) in VISITS.items():
        arguments = capture(bot, visit_name, skill, first_row)
        (TARGET / f"{name}.pkl.xz").write_bytes(
            lzma.compress(pickle.dumps(arguments), preset=PRESET))
        print(name, "written")
        rows = [json.loads(line) for line in
                (CAPTURES / bot / "loadout-report-tail.jsonl").read_text(encoding="utf-8").splitlines()]
        last = next(row for row in reversed(rows)
                    if row.get("candidates") and row["time"] == report_time)
        chosen = last["candidates"][0]
        recorded[name] = {
            "time": last["time"],
            "chosen_band": last["chosen_band"],
            "speed": chosen["score"]["speed"],
            "melee_output": chosen["score"]["melee_output"],
            "slots": {slot: entry["name"] for slot, entry in chosen["slots"].items()},
        }
    (TARGET / "recorded.json").write_text(
        json.dumps(recorded, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
