"""n1-b life-416: an older visit target answered for a light it never compared (2026-11-22 17:12).

Owner 2026-11-22 (Q2, verbatim) 「決まりは足さず、着け直しを記録。往復が起きたら停止して直す。」.
n1-b life-416 (Lv7 Magic-Eater, new character, bot-437d85905) stopped in town on
``town:blocked:equipment-slot-flipflop:light``.  All three wears were the light ranker's
(policy ``_light_to_wield``, the town's ``wield-light`` rung):

* 1375: the 真鍮のランタン {高級品, Q34}, just identified (光明の真鍮のランタン), over the torch -- the rank;
* 1380: a torch over the lantern -- the visit target's answer (n1-a life-534's fix,
  equipment_target ``compared_target_piece``): the held target was the first visit's (epoch
  75001; this visit ran no search), which compared the torches, chose the worn torch (its
  ``search`` row's target_added ``equipped:f53f3657deb1e21d:0``) and saw the lantern only
  unidentified.  Asked about the torch candidate it answered "the torch";
* 1381: the lantern back -- the rank again, the lantern being a piece no target compared.

Root: the reader asked only whether the target compared the candidate.  Fix: the target answers
only when it compared every light of the question -- the worn one included.  The identified
lantern is no piece the old target saw, so the rank (lantern over torch) answers and keeps it.

Recorded (tests/extract_n1b_416_light_flipflop_1122_fixture.py): the restart's town-arrival
checkpoint on the stop's board (rows 0-5 replayed through the public ``choose_key``) and three
boards of the stopped visit from the capture's state.jsonl.

DECLARED CONSTRUCTED:

* the character dump: after the recorded ``periodic:character-dump`` the arrival's dump bytes are
  written again (the replay cannot receive the game's file);
* the held visit target: the restart lost it (it is not in the saved policy state) and its search
  result is not in the capture.  It is the first visit's as its journal row records it: decided
  on the owned set of turn 132166's board (the census of that board's catalogue, the lantern
  unidentified) with the worn set as its loadout (target_added: the worn ids, the torch
  ``equipped:f53f3657deb1e21d:0`` among them).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import hengbot.policy  # noqa: F401 -- import order (circular import when run alone)
from hengbot import equipment_target
from hengbot.equipment_optimizer import current_loadout
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-416-light-flipflop-1122"
LANTERN = "光明の真鍮のランタン"
TORCH = "松明"
FIRST_VISIT_EPOCH = 75001


def _quiet(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args, **kwargs)


def _worn_light(board):
    return next(item for item in board.equipment if item.slot == "light")


class StaleTargetLightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        policy, _journal, steps = _quiet(load, FIXTURE, Path(cls.scratch.name))
        cls.addClassCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        dump = Path(policy._character_dump_path).read_bytes()
        for recorded, supply in steps:
            board = supply()
            _quiet(policy.choose_key, board)
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
            if recorded["reason"] == "periodic:character-dump":
                # DECLARED CONSTRUCTED (module docstring): the game writes the dump.
                Path(policy._character_dump_path).write_bytes(dump)
        boards = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))
        cls.boards = {int(turn): policy._with_cached_skill_exp(
            parse_snapshot(json.loads(line), policy._monrace_knowledge))
            for turn, line in boards.items()}
        # DECLARED CONSTRUCTED (module docstring): the first visit's held target.
        first = cls.boards[132166]
        policy._refresh_carried_equipment_catalog(first)
        catalogue = policy._operational_equipment_catalog(first)
        candidates, pieces = policy._visit_candidate_census(catalogue)
        # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: the restart lost the first visit's held target; its journal row records the worn set as its loadout (module docstring)
        decided = SimpleNamespace(best=SimpleNamespace(loadout=current_loadout(catalogue)))
        setattr(policy, equipment_target.VISIT_TARGET_STATE, equipment_target.VisitTarget(
            FIRST_VISIT_EPOCH, candidates, (False, None, 0, (False, False)), decided, pieces))
        cls.policy, cls.catalogue = policy, catalogue

    def test_recorded_boards(self):
        self.assertTrue(_worn_light(self.boards[132166]).name.startswith(TORCH))
        lantern = [item for item in self.boards[132166].inventory if item.is_lantern]
        self.assertEqual([(item.known, item.name) for item in lantern],
                         [(False, "真鍮のランタン {高級品, Q34}")])
        self.assertTrue(_worn_light(self.boards[132684]).name.startswith(LANTERN))
        self.assertTrue(_worn_light(self.boards[132728]).name.startswith(TORCH))
        worn = current_loadout(self.catalogue).item_at("light")
        self.assertEqual(worn.id, "equipped:f53f3657deb1e21d:0")

    def test_the_old_target_compared_the_torches_not_the_identified_lantern(self):
        board = self.boards[132684]
        torch = next(item for item in board.inventory if item.is_torch)
        lantern = _worn_light(board)
        answer = equipment_target.compared_target_piece(self.policy, "light", torch)
        self.assertTrue(answer.name.startswith(TORCH), answer.name)
        self.assertIsNone(equipment_target.compared_target_piece(self.policy, "light", torch, lantern))

    def test_the_worn_identified_lantern_stays(self):
        """Turn 132684: bot-437d85905 wore the torch here (``wield-light`` 'wh')."""
        board = self.boards[132684]
        self.assertIsNone(self.policy._light_to_wield(board))
        key = _quiet(self.policy.choose_key, board)
        self.assertNotEqual(self.policy.last_reason, "wield-light", key)

    def test_a_worn_torch_still_gives_way_to_the_lantern(self):
        """Turn 132728 (the torch the stale answer wore): the rank wears the lantern, as before."""
        chosen = self.policy._light_to_wield(self.boards[132728])
        self.assertIsNotNone(chosen)
        self.assertTrue(chosen.name.startswith(LANTERN), chosen.name)


if __name__ == "__main__":
    unittest.main()
