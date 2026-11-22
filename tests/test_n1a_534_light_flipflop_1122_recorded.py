"""n1-a life-534: the light slot's two owners (2026-11-22 15:48), one owner now: the visit target.

Owner 2026-11-22 (Q2, verbatim) 「決まりは足さず、着け直しを記録。往復が起きたら停止して直す。」 and
the later 「1往復で決定するなら止める必要はない」 (stop from the second round trip).  n1-a life-534
(Lv20 warrior, bot-411807c7d) stopped three times in a row on
``town:blocked:equipment-slot-flipflop:light`` (15:48:19, 15:48:31, 15:48:44) and retired.

The two owners: the visit target (equipment_target, stage E3) chose the 灼熱の真鍮のランタン
{r火} over the 不朽の眼のフェアノールのランプ -- identified at the first visit's row 10 -- and its
transaction wore the lantern (``equipment-transaction:takeoff`` / ``:equip``); the light ranker
(policy ``_light_to_wield``, torch < lantern < permanent light, called by the town's
"keep a light lit" rung as ``wield-light``) wore the lamp back on the next decision, because a
permanent light outranks a lantern.  The ranker deferred to the optimizer only for an ego torch
beside a lantern, and only while the stored search was ready (1d7df73319); after the
transaction's wear the calibration is stale (``calibration-required``) and nothing deferred.

Fix: a light the visit target compared is the target's answer (equipment_target
``compared_target_piece``); the rank serves only a light no target compared (picked up or
identified since) or a target piece that cannot light now.

Recorded (tests/extract_n1a_534_light_flipflop_1122_fixture.py): the 15:48:31 stop's
town-arrival checkpoint and the journal's rows 0-18, replayed through the public ``choose_key``
(recorded keys posted).  Row 18 is the ranker's recorded ``wield-light`` (the lamp) after the
transaction wore the lantern at rows 14-15.

DECLARED CONSTRUCTED:

* the character dump: the replay cannot receive the game's ``C-f`` file, so after each recorded
  ``periodic:character-dump`` the arrival's dump bytes are written again (as
  tests/test_equip_e4b_shelf_evaluation_1122_recorded);
* the restart case: the visit target cleared (``_equipment_visit_target`` None), as at the third
  stop's arrival after the process restarted (the target is not in the saved policy state).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import hengbot.policy  # noqa: F401 -- import order (circular import when run alone)
from hengbot import equipment_target
from hengbot.equipment_optimizer import equipment_move_identity
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-534-light-flipflop-1122"
LANTERN = "灼熱の真鍮のランタン"
LAMP = "不朽の眼のフェアノールのランプ"
RANKER_ROW = 18


def _quiet(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args, **kwargs)


def _light(items):
    return next((item for item in items if item.slot == "light" or item.is_light), None)


class LightOneOwnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        policy, journal, steps = _quiet(load, FIXTURE, Path(cls.scratch.name))
        cls.addClassCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        dump = Path(policy._character_dump_path).read_bytes()
        cls.decided = []
        for recorded, supply in steps[:RANKER_ROW]:
            board = supply()
            key = _quiet(policy.choose_key, board)
            cls.decided.append((recorded["row"], policy.last_reason, key))
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
            if recorded["reason"] == "periodic:character-dump":
                # DECLARED CONSTRUCTED (module docstring): the game writes the dump.
                Path(policy._character_dump_path).write_bytes(dump)
        cls.policy, cls.journal, cls.steps = policy, journal, steps
        cls.board = steps[RANKER_ROW][1]()

    def test_recorded_rows(self):
        reasons = [entry["reason"] for entry in self.journal]
        self.assertEqual(reasons[14:19], [
            "equipment-transaction:takeoff", "equipment-transaction:equip",
            "equipment-transaction:travel-home", "equipment-transaction:defer-identification",
            "wield-light"])
        worn = {item.slot: item.name for item in self.board.equipment}
        self.assertTrue(worn["light"].startswith(LANTERN), worn["light"])
        self.assertIn(LAMP, [item.name for item in self.board.inventory])

    def test_the_visit_target_chose_the_lantern_over_the_lamp(self):
        lamp = next(item for item in self.board.inventory if item.name == LAMP)
        piece = equipment_target.compared_target_piece(self.policy, "light", lamp)
        self.assertIsNotNone(piece)
        self.assertTrue(piece.name.startswith(LANTERN), piece.name)

    def test_the_transaction_is_the_only_light_writer_of_the_visit(self):
        """Rows 0-17 decided on the branch: the only light moves are the target's transaction."""
        light_moves = [(row, reason) for row, reason, _key in self.decided
                       if reason == "wield-light" or reason.startswith("equipment-transaction:")
                       and reason.split(":")[1] in {"takeoff", "equip"}]
        self.assertEqual(light_moves, [(14, "equipment-transaction:takeoff"),
                                       (15, "equipment-transaction:equip")])

    def test_after_the_transaction_wore_the_lantern_the_ranker_asks_the_target(self):
        """Row 18: bot-411807c7d wore the lamp here (``wield-light`` 'wl', the second round trip)."""
        self.assertIsNone(self.policy._light_to_wield(self.board))
        key = _quiet(self.policy.choose_key, self.board)
        self.assertNotEqual(self.policy.last_reason, "wield-light")
        self.assertNotEqual((self.policy.last_reason, key), ("wield-light", "wl"))

    def test_a_light_no_target_compared_is_still_ranked(self):
        """The restart's arrival (third stop, row 3): no target has answered; the rank wears the
        better light as before (one round trip at most: the target's first decision)."""
        held = getattr(self.policy, equipment_target.VISIT_TARGET_STATE)
        try:
            # DECLARED CONSTRUCTED (module docstring): the visit target cleared, as after a restart.
            setattr(self.policy, equipment_target.VISIT_TARGET_STATE, None)
            chosen = self.policy._light_to_wield(self.board)
        finally:
            setattr(self.policy, equipment_target.VISIT_TARGET_STATE, held)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, LAMP)
        self.assertEqual(equipment_move_identity(chosen),
                         equipment_move_identity(next(item for item in self.board.inventory
                                                      if item.name == LAMP)))


if __name__ == "__main__":
    unittest.main()
