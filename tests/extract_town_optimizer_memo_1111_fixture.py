"""Extract tests/fixtures/town-optimizer-memo-1111/ammo-18172-18196.json.

Source: n1-b life-368's town-arrival checkpoint of 2026-11-11 01:48 (the
incident capture of its 02:12 owner-retired stop), copied read-only from the
viewing server to
C:/hengband-backups/pdca/captures/town-retired-burst-1110/n1-b-life-368/incident-0148.

The visit is replayed through the public chooser (journal rows 0-63) and the
obtainable launcher ammunition (``_obtainable_launcher_ammunition``) and the
launchers of decisions 18172 and 18196 (rows 39, 63) are written out: the
last decision before 18196 that consulted the optimizer, and 18196.

The arrival calibration is the previous level's (26; the board is 27), and the
replay has no game to write the periodic dumps that re-derived it live, so the
calibration is carried to the board's level (its base HP from the board's
maximum HP) and each periodic dump re-publishes it unchanged.  The optimizer
gets a 300 s budget: this machine's search takes 90-110 s, past the live 25 s
budget the viewing server's faster search met.  About four minutes.

    python tests/extract_town_optimizer_memo_1111_fixture.py
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import copy
from dataclasses import asdict, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import hengbot.policy_equipment as policy_equipment
from hengbot.cli import _handle_owner_retirement
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.warrior_equipment_evaluator import modify_stat_value
from hengbot.warrior_loadout_evaluator import constitution_hp_bonus
from replay_town_arrival import adopt_calibration, decisions, journal, restore

CAPTURE = Path("C:/hengband-backups/pdca/captures/town-retired-burst-1110/n1-b-life-368"
               "/incident-0148/town-arrival")
OUTPUT = Path(__file__).with_name("fixtures") / "town-optimizer-memo-1111" / "ammo-18172-18196.json"
ROWS = (39, 63)
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)


def level_calibration(source: Path, board_path: Path, target: Path) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    board = parse_snapshot(json.loads(board_path.read_text(encoding="utf-8")), {})
    player = board.player
    data["level"] = player.level
    data["visible_stat_key"] = list(player.printed_stat_cur_key)
    con_items = sum(each.pval for each in board.equipment if 4 in each.known_flags)
    con = modify_stat_value(data["natural_stats"][4], data["intrinsic_adjustments"][4] + con_items)
    data["base_hp"] = player.max_hp - constitution_hp_bonus(con, player.level)
    target.write_text(json.dumps(data), encoding="utf-8")


def republish(self, pending, character, envelope, board=None):
    """A periodic dump: the same constants, a new observation."""
    previous = self._character_calibration
    self._character_calibration = replace(previous, observed_turn=previous.observed_turn + 1)
    self._character_calibration_loaded = True
    self._calibration_unavailable_reason = None
    self._calibration_rejection = None


def item_row(each):
    return dict(asdict(each), _type=type(each).__name__)


def main() -> None:
    HengbotPolicy._publish_character_dump = republish
    search = policy_equipment.prepare_warrior_optimization
    policy_equipment.prepare_warrior_optimization = (
        lambda *args, **kwargs: search(*args, **{**kwargs, "timeout_seconds": 300.0}))
    rows = []
    with TemporaryDirectory() as raw:
        scratch = Path(raw)
        policy = restore(CAPTURE, scratch)
        leveled = scratch / "calibration" / "character-calibration.json"
        leveled.parent.mkdir()
        level_calibration(CAPTURE / "sidecars" / "_character_calibration_path",
                          CAPTURE / "board.json", leveled)
        adopt_calibration(policy, leveled, scratch)
        recorded = journal(CAPTURE)
        for index, (row, supply) in enumerate(decisions(policy, CAPTURE, scratch)):
            if index > max(ROWS):
                break
            board = supply()
            if index in ROWS:
                rows.append({
                    "row": index,
                    "decision_sequence": recorded[index]["decision_sequence"],
                    "ammunition": [item_row(each)
                                   for each in policy._obtainable_launcher_ammunition(board)],
                    "launchers": [asdict(each) for each in (*board.equipment, *board.inventory)
                                  if each.ammo_tval is not None and not each.is_ammo],
                })
            visit_before = copy.copy(policy._store_visit)
            key = policy.validate_read_key(board, policy.choose_key(board))
            key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=sorted) + "\n",
                      encoding="utf-8", newline="\n")
    print(OUTPUT, [len(row["ammunition"]) for row in rows])


if __name__ == "__main__":
    main()
