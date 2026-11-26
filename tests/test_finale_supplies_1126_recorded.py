"""n1-c life-222's finale supplies step stopped as not-at-home with 46 Restore Mana at Home.

Recorded (tests/fixtures/n1c-222-finale-supplies-1126.json.gz, extracted by
tests/extract_n1c_222_finale_supplies_1126_fixture.py from the capture
``20261126-090930-loop-detected``, build bot-5175c3635): the 99F/100F preparation phase reached
its supplies step at decision 2930; the Home pass's shortage queue
(``home:queue-catalogue-shortage``, decision 2934) bound the *Healing* and the Restore Mana the
step was taking, and when the step's own takes emptied the first entry the queue gave both up
for the visit (``_deferred_home_items``, recorded from decision 2937 on).  On decision 2940 the
step had taken the Healing, the *Healing* and the Resistance; the census held 46 Restore Mana,
the pack none, and the step read the deferred stack as absent and stopped as
``supplies:not-at-home:75-40``.  The town then stopped under
``town:blocked:finale-prep-stopped:supplies:not-at-home:75-40`` (owner-halted 09:09:36) with every
supply owned (the report's ``owned`` rows all ready).

DECLARED CONSTRUCTED:
* a fresh policy holding the recorded census as its current, complete Home catalogue and the
  recorded deferral set, its phase at the supplies step in town;
* the board's monster lists emptied (the town's people: no monster knowledge is loaded);
* ``angband_finale.restore_mana_carry`` answering the board's recorded required carry (46: the
  absorbed rockets' plan is the capture's, not this policy's).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from hengbot import angband_finale, finale_prep
from hengbot.item_identity import memory_identity_of_signature
from hengbot.model import _parse_items, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.protocol import snapshot_protocol_version

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-finale-supplies-1126.json.gz"


def recorded():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()).decode("utf-8"))


def stopped_board():
    record = recorded()
    policy = HengbotPolicy()
    census = record["census"]
    items = tuple(_parse_items(census["knowledge"]["items"],
                               protocol=snapshot_protocol_version(census)))
    board_data = dict(record["board"], visible_monsters=[], detected_monsters=[])
    board = parse_snapshot(board_data, policy._monrace_knowledge)
    policy._home_knowledge_items = items
    policy._home_knowledge_valid_before = len(items)
    policy._home_knowledge_current, policy._home_knowledge_invalidated = True, False
    policy._equipment_catalog.home_scan_complete = True
    for name, tval, sval in record["deferred"]:
        policy._deferred_home_items.add((name, tval, sval))
    held = finale_prep.phase(policy)
    held.step, held.in_town = finale_prep.SUPPLIES, True
    return policy, board, record


class FinaleSuppliesDeferredStackTest(unittest.TestCase):
    def test_the_recorded_board(self):
        policy, board, record = stopped_board()
        self.assertTrue(board.in_town)
        self.assertEqual(angband_finale.carried(board, angband_finale.RESTORE_MANA), 0)
        stacks = [item for item in policy._home_knowledge_items
                  if (item.tval, item.sval) == angband_finale.RESTORE_MANA]
        self.assertEqual([item.count for item in stacks], [46])
        self.assertEqual(record["restore_mana_carry"], 46)
        # The recorded deferral names the census's Restore Mana stack (and the *Healing*).
        deferred = {memory_identity_of_signature(tuple(entry)) for entry in record["deferred"]}
        self.assertIn(memory_identity_of_signature(policy._item_signature(stacks[0])), deferred)
        self.assertIn(policy._item_signature(stacks[0]), policy._deferred_home_items)
        for kind in (angband_finale.HEALING, angband_finale.STAR_HEALING,
                     angband_finale.RESISTANCE, angband_finale.TELEPORT):
            self.assertGreaterEqual(angband_finale.carried(board, kind), angband_finale.CARRY[kind])

    def test_a_stack_another_take_deferred_is_taken_not_a_stop(self):
        policy, board, record = stopped_board()
        held = finale_prep.phase(policy)
        with patch.object(angband_finale, "restore_mana_carry",
                          return_value=record["restore_mana_carry"]):
            self.assertIsNone(finale_prep.town_key(policy, board))
        self.assertIsNone(held.stopped)  # recorded: supplies:not-at-home:75-40
        self.assertEqual(held.step, finale_prep.SUPPLIES)
        request = policy._home_errand.request
        self.assertEqual(request.purpose, finale_prep.PURPOSE)
        self.assertEqual(request.signature[1:], angband_finale.RESTORE_MANA)
        self.assertEqual(request.quantity, 46)


if __name__ == "__main__":
    unittest.main()
