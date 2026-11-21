"""n1-b life-413: *Destruction* replaced by a step off a poison swamp, killed by ソーラー (2026-11-22).

life-413 (Magic-Eater Lv38, Zombie, HP 748, the absorbed *Destruction* at 87% with 19 charges)
recalled to Angband 80F at 04:18:42 and walked a poison swamp (immobile-threat:approach-to-shoot
toward the 天使・クイルスルグ seen on arrival).  After the redetection on (19,33) (HP 538):

 - turn 3100989, HP 519: 天使・クイルスルグ summoned angels, ソーラー (sensed) healed.  The emergency
   ladder answered with the absorbed *Destruction* (``mA3`` emergency:destruction:absorbed-power);
   damaging_ground.leave_first (owner 2026-11-04 「先に出る」, device uses included) replaced it with
   ``1`` hazard:step-off, onto (20,32), still on the swamp.
 - turn 3100996, HP 491: the replaced use read as a failed one (destruction_use ``observe``:
   no flash, a new turn), *Destruction* was no longer usable, and deep_teleport's substitute read
   Word of Recall (``rh`` deep-teleport:recall).
 - turn 3100999, HP 491, the 即死 board (next action p95 542, a プラネター beside): the line of
   fire's p95 189 < HP refused the teleport (owner 2026-11-14) and deep_teleport answered with
   *Destruction* (emergency:destruction:deep-teleport:absorbed-power), replaced again by
   ``1`` hazard:step-off.  ソーラー's mana bolt and starburst and the プラネター's blows: HP -160.

The fix (damaging_ground.step_off_key): a *Destruction* use (destruction_use ``used_now``) stays,
as the teleport read it stands in for stays.

Recorded (tests/fixtures/n1b-413-solar-death-1122, see
tests/extract_n1b_413_solar_death_1122_fixture.py): the town-arrival checkpoint and its 73
journal rows, then the 62 boards of 80F with their decision rows.  The recorded keys are posted
(the replay's town rows differ where the journal's store screens are not reconstructed).

DECLARED RECONSTRUCTED: ``_me_power_resume_reads`` as the live CLI sets it.  The power-list
screens of 80F are not delivered (the new floor's map-area, trap detection and light rows
replay differently; the death's boards do not depend on them).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import damaging_ground, destruction_use
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-solar-death-1122"
FIRST_STEP_OFF, RECALL_READ, DEATH = 3100989, 3100996, 3100999


def _post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1b413SolarDeath1122RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name) / "fixture")
        policy._me_power_resume_reads = True  # DECLARED: the live CLI's
        floor = json.loads(lzma.decompress((FIXTURE / "floor.json.xz").read_bytes()).decode(
            "utf-8", "surrogateescape"))
        with contextlib.redirect_stdout(io.StringIO()):
            for recorded, supply in steps:
                policy.choose_key(supply())
                _post(policy, recorded["key"])
            decisions = list(floor["decisions"])
            cls.replayed, cls.boards = {}, {}
            for index, raw in enumerate(floor["boards"]):
                board = parse_snapshot(raw, policy._monrace_knowledge)
                key = policy.choose_key(board)
                # The arrival turn's first board: no decision of its own (the next board's).
                if index + 1 < len(floor["boards"]) and floor["boards"][index + 1]["turn"] == raw["turn"]:
                    continue
                recorded = decisions.pop(0)
                assert recorded["turn"] == raw["turn"], (recorded["turn"], raw["turn"])
                cls.replayed[raw["turn"]] = (key, policy.last_reason, recorded,
                                             destruction_use.used_now(policy, board))
                cls.boards[raw["turn"]] = board
                _post(policy, recorded["key"])
        cls.policy = policy

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    # ------------------------------------------------------------ the record

    def test_the_record_steps_off_twice_and_dies(self):
        recorded = {turn: (row[2]["key"], row[2]["reason"]) for turn, row in self.replayed.items()}
        self.assertEqual(recorded[FIRST_STEP_OFF], ("1", "hazard:step-off"))
        self.assertEqual(recorded[RECALL_READ], ("rh", "deep-teleport:recall"))
        self.assertEqual(recorded[DEATH], ("1", "hazard:step-off"))
        death = self.boards[DEATH]
        self.assertEqual((death.dungeon_level, death.player.hp, death.player.max_hp), (80, 491, 748))
        self.assertTrue(death.player.recalling)
        for turn in (FIRST_STEP_OFF, DEATH):
            self.assertTrue(damaging_ground.hurts_here(self.policy, self.boards[turn]), turn)
        self.assertIn("ソーラーは完全に治った！", self.replayed[FIRST_STEP_OFF][2]["messages"])

    def test_the_walk_over_the_swamp_replays_as_recorded(self):
        walk = [turn for turn, row in self.replayed.items()
                if row[2]["reason"] == "immobile-threat:approach-to-shoot"]
        self.assertEqual(len(walk), 23)
        for turn in walk:
            key, reason, recorded, _used = self.replayed[turn]
            self.assertEqual((key, reason), (recorded["key"], recorded["reason"]), turn)

    # ------------------------------------------------------------ the pins

    def test_the_emergency_destruction_is_not_replaced_by_the_step_off(self):
        key, reason, _recorded, used = self.replayed[FIRST_STEP_OFF]
        self.assertEqual((key, reason), ("mA3", "emergency:destruction:absorbed-power"))
        self.assertTrue(used)

    def test_the_deep_teleport_destruction_on_the_instant_death_board_stays(self):
        key, reason, _recorded, used = self.replayed[DEATH]
        self.assertEqual((key, reason), ("mA3", "emergency:destruction:deep-teleport:absorbed-power"))
        self.assertTrue(used)

    def test_a_standstill_on_the_swamp_still_steps_off(self):
        """Owner 2026-11-04 「先に出る」 holds for every other standstill on the death board."""
        board = self.boards[DEATH]
        destruction_use._memory(self.policy).pending = None  # no use answered this ask
        key = damaging_ground.step_off_key(self.policy, board, "s")
        self.assertIsNotNone(key)
        self.assertEqual(self.policy.last_reason, damaging_ground.STEP_REASON)


if __name__ == "__main__":
    unittest.main()
