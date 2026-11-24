"""A Magic-Eater menu label names only its own decision's key (n1-c life-221, 2026-11-24 16:56).

The owner halt ``stuck-prompt:ranged:magic-eater-device`` left no prompt open: the stop line reads
``ctx=command ctx_prompt=""``, ``phase=admission``, ``invalid Magic-Eater device attack``.  Decision
12403 zapped the absorbed rod (``mCv8``) at the 不潔な病人 that woke north of the player on the way
to the Armoury; the rod killed it.  Decision 12404 had no hostile left and the full Home's relief
walked on toward the Armoury (``_home_full_relief_route_key`` -> ``_shopping_approach_key``, step
``7``), a producer that names its walk only when no reason of this decision stands
(``_home_relief_names_approach``).  ``ranged:magic-eater-device``, set by the previous decision's
``me_device_attacks._prefix``, still stood, so the step was posted under it and the device compiler
(``me_device_attacks_input.compile_device``), which owns every key under that label, refused ``7``.

The fix: a label under which a Magic-Eater menu use refuses every key but its own
(``me_powers.menu_owned_label``) is dropped when the next public decision starts
(``HengbotPolicy.choose_key`` -> ``me_powers.drop_standing_label``); its producer sets it again
with each key it composes.

Attacking the town monster itself is the existing rule: the 不潔な病人 was awake and adjacent, the
town hunt (``_town_kill_mob_key``) hands an adjacent hostile to the survival rungs, and the
Magic-Eater's adjacent shot weighs the absorbed powers against the blow
(``_adjacent_ranged_key``, owner 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を使用する」).

Recorded (tests/extract_n1c_221_me_rod_town_1124_fixture.py, ``n1c-221-me-rod-town-1124``): the
town-arrival checkpoint of 16:56:13 (decision 12376) and its 28 journal rows.  Rows before the one
decided are replayed through the public ``choose_key`` and post the recorded key; rows 11 and 12
(the second equipment-transaction deposit, decisions 12388-12389) decide one deposit fewer on the
current code and are posted as recorded.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.input_executor import ScreenKind
from hengbot.magic_eater import ABSORB_REASON, MISSILE_REASON
from hengbot.me_device_attacks import DEVICE_REASON, POWERFUL_REASON
from hengbot.me_menu_uses import compile_menu_key
from hengbot.me_powers import menu_owned_label
from hengbot.me_powers_refresh import REFRESH_REASON
from hengbot.observed_input import compile_observed_input
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-221-me-rod-town-1124"
ROD_ROW, WALK_ROW = 26, 27
ROD = ("mCv8", DEVICE_REASON)
WALK_KEY = "7"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


class MeRodTownLabel1124RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        policy, journal, steps = load(FIXTURE, Path(scratch.name))
        cls.journal = journal
        cls.recorded = [(row["key"], row["reason"]) for row in journal]
        for recorded, supply in steps[:ROD_ROW]:
            decide(policy, supply())
            post(policy, recorded["key"])
        cls.rod = decide(policy, steps[ROD_ROW][1]())
        cls.label_after_rod = policy.last_reason
        post(policy, steps[ROD_ROW][0]["key"])
        cls.walk = decide(policy, steps[WALK_ROW][1]())

    def raw(self, row):
        return json.loads(self.journal[row]["line"])

    def test_the_recording_walked_under_the_rod_label(self):
        self.assertEqual(self.recorded[ROD_ROW], ROD)
        self.assertEqual(self.recorded[WALK_ROW], (WALK_KEY, DEVICE_REASON))
        # No prompt was open: the refused key was decided on a command board.
        self.assertEqual(self.raw(WALK_ROW)["visible_monsters"], [])

    def test_the_device_compiler_refuses_a_step_under_its_label(self):
        """The recorded halt: '7' under ``ranged:magic-eater-device`` at admission."""
        with self.assertRaisesRegex(ValueError, "invalid Magic-Eater device attack"):
            compile_observed_input(WALK_KEY, ScreenKind.COMMAND, self.raw(WALK_ROW),
                                   DEVICE_REASON, [])

    def test_the_rod_is_decided_as_recorded(self):
        self.assertEqual(self.rod, ROD)
        self.assertEqual(self.label_after_rod, DEVICE_REASON)
        prefix, steps = compile_observed_input(ROD[0], ScreenKind.COMMAND, self.raw(ROD_ROW),
                                               ROD[1], [])
        self.assertEqual(prefix, "m")
        self.assertTrue(steps)

    def test_the_next_walk_is_named_by_its_own_producer(self):
        key, reason = self.walk
        self.assertEqual(key, WALK_KEY)
        self.assertEqual(reason, "shop:approach")
        self.assertFalse(menu_owned_label(reason))
        # The step is admitted as an ordinary command key.
        self.assertEqual(compile_observed_input(key, ScreenKind.COMMAND, self.raw(WALK_ROW),
                                                reason, []), (WALK_KEY, []))


class ClaimedLabelTest(unittest.TestCase):
    def test_the_labels_the_menu_compilers_own(self):
        for owner in (DEVICE_REASON, POWERFUL_REASON, ABSORB_REASON, MISSILE_REASON,
                      "me-power:dark-room:lite-area", "emergency:destruction:absorbed-power"):
            with self.subTest(owner=owner):
                self.assertTrue(menu_owned_label(owner))

    def test_the_compilers_refuse_a_step_under_exactly_these_labels(self):
        """``menu_owned_label`` is the compilers' own refusal, not a second list."""
        for owner in (DEVICE_REASON, POWERFUL_REASON, ABSORB_REASON, MISSILE_REASON,
                      "me-power:dark-room:lite-area", "emergency:destruction:absorbed-power"):
            with self.subTest(owner=owner):
                with self.assertRaises(ValueError):
                    compile_menu_key(WALK_KEY, owner)
        for owner in ("shop:approach", "me-powerful:identify", REFRESH_REASON):
            with self.subTest(owner=owner):
                self.assertIsNone(compile_menu_key(WALK_KEY, owner))

    def test_control_other_labels(self):
        # The Powerful Activation's own uses and the browse refresh claim only their keys' shape.
        for owner in ("shop:approach", "ranged:fire", "melee", "me-powerful:identify",
                      REFRESH_REASON, "", None):
            with self.subTest(owner=owner):
                self.assertFalse(menu_owned_label(owner))


if __name__ == "__main__":
    unittest.main()
