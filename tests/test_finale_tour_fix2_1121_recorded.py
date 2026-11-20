"""The 99F/100F Teleportation bought where the shelf has them, and a circuit that ends with its trip.

Owner 2026-11-20 「テレポートの巻物を大量に持つ」 (40) and 「4つの街を回ってテレポートの巻物を買い足す
処理をつけて」 (finale_teleport_tour).  n1-c life-217's visit of 2026-11-21 03:49:31-03:50:13
(bot-5de5adae3) held 23 of the 40, entered the Alchemist of all four towns (each with 59-99
Teleportation on its shelf at 50-56 gold) and left every one with nothing bought, then read the
recall in town 3:

* the shop selector (``_legacy_next_purchase_unreserved``) picked a Teleportation only for the
  supply ledger's own count; the finale's 40 raised the quantity of such a buy but never chose one
  (the rung ``tail:angband-finale`` only matched it), so with the ledger met the page wanted nothing;
* the circuit the previous visit started at its recall read stayed installed through the dungeon
  (``forget_trip`` cleared only the circuit's flag): this visit it was an ordinary Teleportation
  expedition under way, and the circuit was never due.

Recorded: that visit's town-arrival checkpoint and its whole journal (tests/
extract_finale_tour_fix2_1121_fixture.py), replayed through ``choose_key``.

DECLARED CONSTRUCTED: in the trip test, the circuit's flag set as the previous visit's start left
it (the arrival's funds record is that circuit's: angband-finale-teleport, town 3 tried) and the
arrival board as an Angband 95F board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import angband_finale, finale_teleport_tour
from hengbot.model import DUNGEON_ANGBAND, STORE_ALCHEMIST
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-217-finale-tour-fix2-1121"
FIRST_ALCHEMIST_DONE = 47  # the journal row: town 0's Alchemist page after its recall buy


class FinaleTourFix2RecordedTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, self.steps = load(FIXTURE, Path(self.scratch.name))

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def test_the_first_alchemist_sells_the_seventeen(self):
        policy = self.policy
        for recorded, supply in self.steps:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            if recorded["row"] == FIRST_ALCHEMIST_DONE:
                break
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]),
                             recorded["row"])
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        self.assertEqual((recorded["key"], recorded["reason"]), ("\x1b", "shop:in-store-done"))
        self.assertEqual(policy._effective_town_id(board), 0)
        self.assertEqual(board.store.store_type, STORE_ALCHEMIST)
        self.assertEqual(angband_finale.carried(board, angband_finale.TELEPORT), 23)
        self.assertEqual(finale_teleport_tour.shortage(policy, board), 17)
        scroll = next(item for item in board.store.items if item.is_teleport_scroll)
        self.assertEqual((scroll.count, scroll.price), (99, 53))
        self.assertEqual(policy.last_reason, "shop:in-store-buy")
        self.assertEqual(key, f"p{scroll.letter}17\r\r")

    def test_the_trip_ends_the_circuit(self):
        policy = self.policy
        recorded, supply = self.steps[0]
        board = supply()
        self.assertEqual(policy._cross_town_shopping_funds["circuit"], "angband-finale-teleport")
        left = policy._cross_town_shopping
        self.assertEqual((left.trigger_town_id, left.tried_towns), (3, [3]))
        setattr(policy, finale_teleport_tour.STATE, True)  # DECLARED: as the start left it
        dungeon = replace(board, floor_key=(DUNGEON_ANGBAND, 95, 0), town_flag=False)
        angband_finale.observe(policy, dungeon)
        self.assertIsNone(policy._cross_town_shopping)
        self.assertIsNone(finale_teleport_tour.circuit(policy))


if __name__ == "__main__":
    unittest.main()
