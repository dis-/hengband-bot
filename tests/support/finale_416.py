"""The replay of n1-b life-416's recorded Angband 99F boards (Oberon, 2026-11-23 18:29-18:52).

The boards are the snapshots of that floor (jsonlog/snapshots, player_turn lines only); the replay
is open-loop: each board is the recorded one, whatever key the policy sends.  A use the policy
sends is answered on the next board as the executor would (``_completed_operation_owner``), so
me_powers counts it.

DECLARED RECONSTRUCTED: the finale's expedition mark (finale_prep ``lifted``) and the
Magic-Eater's device lists (the snapshot files carry none; the decisions of that floor show these
powers cast): staffs *Destruction*, Teleportation, Magic Mapping, Speed, Healing (30 each); wands
Stone to Mud (60) and Rocket (30); rods Detection (5) and Restoration (3); all at 95%.

DECLARED CONSTRUCTED: a board that recorded the food state "normal" reads "full" (the battle's
eat ahead below full, angband_finale_battle ``_bank_food_key`` of 2026-11-26, done before the
window: the recorded runs predate it).  With ``eat_ahead`` the recorded state is kept until the
policy eats ahead (``BANK_FOOD_REASON``), and the later boards read "full" as the game would answer
(+5000 food from below PY_FOOD_FULL).
"""
from __future__ import annotations

import contextlib
import copy
import gzip
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale_battle, finale_prep, me_capability
from hengbot.model import parse_snapshot

from tests.support.recorded import _policy

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
LISTS = {"staff": ((29, 30), (4, 30), (9, 30), (22, 30), (18, 30)),
         "wand": ((6, 60), (29, 30)), "rod": ((6, 5), (10, 3))}


def device_lists(turn: int) -> dict:
    return {kind: (turn, tuple({"name": me_capability.names(kind, sval)[0], "current": count,
                                "max": count, "charging": 0, "fail": 5, "success": 95}
                               for sval, count in rows))
            for kind, rows in LISTS.items()}


def boards(name: str) -> list:
    """The player_turn boards of a fixture.  A row may carry ``_same``: the fields equal to the
    previous row's, left out of the file (the 100F floor's 1507 boards, 7.7 MB whole)."""
    rows, previous = [], None
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            same = row.pop("_same", ())
            if same:
                row = {**{key: previous[key] for key in same}, **row}
            previous = row
            rows.append(row)
    return [row for row in rows if row.get("type") == "player_turn"]


def drive(raw_boards, monrace, *, prepare=None, eat_ahead=False) -> list:
    """(turn, (y, x), key, reason, phase, last_seen, target cell) of each board.  ``prepare``
    (policy, snapshot) runs before each decision (a DECLARED constructed state)."""
    directory = TemporaryDirectory()
    try:
        policy = _policy(Path(directory.name), monrace)
        first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw_boards[0]), monrace))
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        held = finale_prep.phase(policy)
        held.lifted, held.step = True, finale_prep.DONE
        decided, owner, banked = [], None, not eat_ahead
        for raw in raw_boards:
            raw = copy.deepcopy(raw)
            if owner:
                raw["_completed_operation_owner"] = owner
            if banked and (raw.get("player") or {}).get("food_state") == "normal":
                raw["player"]["food_state"] = "full"
            board = policy.with_known_skill_exp(parse_snapshot(raw, monrace))
            policy._me_device_lists = device_lists(board.turn)
            if prepare is not None:
                prepare(policy, board)
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            battle = getattr(policy, angband_finale_battle.MEMORY, None)
            target = angband_finale_battle.target_monster(board)
            decided.append((board.turn, (board.player.position.y, board.player.position.x), key,
                            policy.last_reason, battle.phase if battle else None,
                            battle.last_seen if battle else None,
                            (target.position.y, target.position.x) if target else None))
            owner = policy.last_reason if key else None
            banked = banked or (bool(key) and policy.last_reason
                                == angband_finale_battle.BANK_FOOD_REASON)
            if key:
                policy.confirm_key_posted(key)
        return decided
    finally:
        directory.cleanup()
