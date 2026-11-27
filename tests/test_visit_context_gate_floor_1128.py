"""The visit target's context carries the unmet speed row's floor (five fields) without a crash.

2026-11-28 06:25: bot-1a72153ac crashed in every town (``ValueError: too many values to unpack
(expected 4, got 5)``, equipment_target.redecide_events) after the context gained the gate
floor; n1-a, n1-b halted and n1-c lost two new characters to the crash escalation.
"""
import unittest
from types import SimpleNamespace

from hengbot import equipment_target


def _held(context):
    return SimpleNamespace(context=context, candidates=(), pieces=())


class VisitContextGateFloorTest(unittest.TestCase):
    def _events(self, held_context, context):
        held = _held(held_context)
        original = equipment_target.candidate_gains
        equipment_target.candidate_gains = lambda *_: ((), ())
        try:
            return equipment_target.redecide_events(held, (), context)
        finally:
            equipment_target.candidate_gains = original

    def test_five_field_context_with_same_held_decides_nothing(self):
        context = ("idle", 80, 91, 9, (True, False))
        self.assertEqual(self._events(context, context), ())

    def test_gate_floor_appearing_redecides(self):
        held = ("idle", 80, None, 9, (True, False))
        context = ("idle", 80, 91, 9, (True, False))
        self.assertEqual(self._events(held, context),
                         (equipment_target.EVENT_DESTINATION_FLOOR,))

    def test_target_held_with_four_fields_is_read(self):
        held = ("idle", 80, 9, (True, False))
        context = ("idle", 80, None, 9, (True, False))
        self.assertEqual(self._events(held, context), ())

    def test_floor_and_gate_both_moving_name_the_event_once(self):
        held = ("idle", 70, None, 9, (True, False))
        context = ("idle", 80, 91, 9, (True, False))
        self.assertEqual(self._events(held, context),
                         (equipment_target.EVENT_DESTINATION_FLOOR,))


if __name__ == "__main__":
    unittest.main()
