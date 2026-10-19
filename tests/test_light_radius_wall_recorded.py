"""The pre-2026-10-19 light wall is not vacuous (issue #86 round 4).

``tests/recorded_loadout.py`` declares ``pre_light_radius_rule`` for recorded
replays whose subject is not the light choice.  This pin shows the wall on the
board where the branch first diverges from the recorded trajectory: the tour
capture (tests/test_unaffordable_claim_tour_recorded.py), decision index 2,
the first optimizer call of the replay.  There the worn フェアノールのランプ
(radius 2) and the Home ★ガラドリエルの玻璃瓶 (radius 3) give identical modeled
combat results; the decision 「照らせる範囲も比べる」 picks the Phial, the wall
keeps the lamp the recorded boards keep.

Substrate: decisions 0-1 replayed through the public response path, the board
of decision 2 decided once (as the replays do, under recorded_loadout_replay);
the optimizer inputs of that decision's first call are recorded by a spy that
calls through and evaluated again with and without the wall.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot import warrior_optimization
from hengbot.cli import _consume_response_sequence
from hengbot.equipment_optimizer import SLOT_LIGHT, permanent_light_radius
from recorded_loadout import pre_light_radius_rule, recorded_loadout_replay
import test_unaffordable_claim_tour_recorded as tour


FIRST_CHANGED = 2
LAMP_ID = "equipped:21b109e0d6b6382d:0"
PHIAL_ID = "home:1238e7da3d947a78:0"


class PreLightRadiusWallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tour.UnaffordableClaimTourRecordedTest.setUpClass()
        cls.replay = tour.UnaffordableClaimTourRecordedTest

    @recorded_loadout_replay
    def _first_optimizer_call(self):
        replay = self.replay
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy, monrace = tour._live_like_policy(directory)
            cursor = 0
            for index in range(FIRST_CHANGED + 1):
                count = replay.boundaries["input_rows"][index]
                segment = replay.lines[cursor:cursor + count]
                cursor += count
                _decoded, snapshots = _consume_response_sequence(
                    segment, policy, lambda _key: True, monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                snapshot = snapshots[-1]
                policy._experience_drain_known = tour._drain_unknown
                if index == FIRST_CHANGED:
                    with patch.object(
                        warrior_optimization, "optimize_loadout",
                        wraps=warrior_optimization.optimize_loadout,
                    ) as spy:
                        policy.choose_key(snapshot)
                    self.assertTrue(spy.call_args_list)
                    args, kwargs = spy.call_args_list[0]
                    break
                key = policy.choose_key(snapshot)
                key = policy.validate_read_key(snapshot, key)
                self.assertEqual(
                    [str(key), policy.last_reason],
                    replay.boundaries["recorded"][index],
                )
                register = policy._claim_register
                policy._claim_register = copy.copy(register)
                tour._recorded_process_capture(policy, snapshot)
                policy._claim_register = register
                policy.confirm_key_posted(key)
            optimize = warrior_optimization.optimize_loadout
            unwalled = optimize(*args, **kwargs)
            with pre_light_radius_rule():
                walled = optimize(*args, **kwargs)
        return unwalled, walled

    def test_without_the_wall_the_phial_with_the_wall_the_lamp(self):
        unwalled, walled = self._first_optimizer_call()
        phial = unwalled.best.loadout.item_at(SLOT_LIGHT)
        lamp = walled.best.loadout.item_at(SLOT_LIGHT)
        self.assertEqual((phial.id, permanent_light_radius(phial)), (PHIAL_ID, 3))
        self.assertEqual((lamp.id, permanent_light_radius(lamp)), (LAMP_ID, 2))
        # Only the light differs; the modeled combat results are identical.
        self.assertEqual(
            unwalled.best.loadout.item_ids - {PHIAL_ID},
            walled.best.loadout.item_ids - {LAMP_ID},
        )
        self.assertEqual(unwalled.best.metrics, walled.best.metrics)


if __name__ == "__main__":
    unittest.main()
