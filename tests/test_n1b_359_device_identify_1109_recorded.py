"""n1-b life-359 2026-11-09: the town device identification casts the absorbed Identify.

Owner 2026-10-30 「以降、鑑定と財宝感知は取り込みで賄う」: the absorbed Identify
serves what a staff would.  The town equipment identification composes it first
(``_carried_identify_command``; its admission since this life's overflow stop,
tests/test_n1b_359_overflow_1109_recorded.py), but ``_town_device_processing_key``
-- the unknown wands and staffs -- and its admission (town_terminal
``gather_identify_device``) asked a carried reliable scroll or staff only and
requested a scroll from the Alchemist instead.  The life carried six unknown
devices (Trap disarm, Frost bolt x2, an unknown wand, Summoning, Slow Monster)
at 21/23, where the town pack budget refuses a new scroll stack.

Recorded: the town-arrival checkpoint of tests/fixtures/n1b-359-overflow-1109/,
rows 0-8 decided as recorded through the public ``choose_key``.
DECLARED CONSTRUCTED: the row-9 board with the five unknown pieces of
armour and weapons taken out (the equipment identification owns those and
runs first), so the device identification is the next owner; the key goes
through the production executor into the overflow test's engine
(``IdentifyingHomeGame``: the absorbed Identify lands, the device known with
its charges read as 0).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import time
import unittest

from hengbot import me_capability
from hengbot.cli import _ExecutorInputPort, _send_new_decision_key
from hengbot.model import SV_STAFF_IDENTIFY, parse_snapshot
from tests import test_n1b_359_overflow_1109_recorded as overflow
from tests.test_n1b_359_overflow_1109_recorded import CAST_ROW, PIECES, IdentifyingHomeGame

DEVICES = ["トラップ解除の魔法棒", "アイス・ボルトの魔法棒", "アイス・ボルトの魔法棒",
           "謎の魔法棒", "召喚の杖", "スロウ・モンスターの杖"]


class N1b359DeviceIdentify1109RecordedTest(overflow.N1b359Overflow1109RecordedTest):
    # Only this module's test runs here; the harness comes from the overflow test.
    test_recorded_visit_walked_for_a_scroll_and_stopped = None
    test_absorbed_identify_identifies_and_the_pack_is_freed = None
    test_plain_armour_with_a_resist_is_kept = None

    def test_unknown_devices_are_identified_with_the_absorbed_power(self):
        policy, _board, entries = self.to_row(CAST_ROW)
        outside = self.raw(entries, CAST_ROW)
        # DECLARED CONSTRUCTED (module docstring): the pieces taken out.
        outside["inventory"] = [item for item in outside["inventory"]
                                if item["name"] not in PIECES]
        for index, item in enumerate(outside["inventory"]):
            item["slot"] = chr(ord("a") + index)
        board = parse_snapshot(copy.deepcopy(outside), policy._monrace_knowledge)
        self.assertEqual([item.name for item in board.inventory if not item.known], DEVICES)
        self.assertIsNone(policy._find_identification_source(board, full=False))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("mAfg", "identify:device"))
        self.assertIsNone(policy._identification_need)

        game = IdentifyingHomeGame(
            pack=copy.deepcopy(outside["inventory"]),
            equipment={item["slot"]: item for item in copy.deepcopy(outside["equipment"])},
            inside=False, state_template=copy.deepcopy(outside))
        game.identified, game.destroyed = [], []
        row = me_capability.observed_row(policy, "staff", SV_STAFF_IDENTIFY)
        game.power_row = (row["current"], row.get("max") or row["current"])
        game.entrance = (-1, -1)
        game.position = (outside["player"]["y"], outside["player"]["x"])
        game.turn = outside["turn"]
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 5).outcome,
                         "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=policy)
        reasons = [(key, policy.last_reason)]
        current = board
        while policy.last_reason == "identify:device" and len(reasons) <= len(DEVICES):
            _send_new_decision_key(
                port, json.dumps(game._state()), key, None, set(),
                in_store=False, snapshot=current,
                decision={"sequence": policy._decision_sequence,
                          "reason": policy.last_reason, "key": key})
            self.assertEqual(port.last_result.outcome, "completed",
                             (reasons, port.last_result.reason))
            self.post(policy, key)
            current = parse_snapshot(port.last_result.board, policy._monrace_knowledge)
            key = policy.choose_key(current)
            reasons.append((key, policy.last_reason))
        # Every device is identified where it lies, no scroll is sought.
        self.assertEqual(game.identified, DEVICES, reasons)
        self.assertEqual([k[:3] for k, reason in reasons if reason == "identify:device"],
                         ["mAf"] * len(DEVICES))
        self.assertNotIn("shop:travel", [reason for _key, reason in reasons], reasons)
        self.assertIsNone(policy._identification_need)


if __name__ == "__main__":
    unittest.main()
