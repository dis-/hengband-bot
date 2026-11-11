"""The equipment optimizer memo on a stable town board (n1-b life-368, 2026-11-11).

n1-b life-368 stayed 22 minutes in town (the guard retired it at 02:12): its
town decisions took 13-47 s, each re-running the whole loadout search.  The
replay of the 01:48 town-arrival checkpoint
(C:/hengband-backups/pdca/captures/town-retired-burst-1110/n1-b-life-368/
incident-0148) reproduces every slow decision of its slow-decision record:

- the decision-row facts (cli._PolicyObserverScope) ran the search on a
  memo miss and discarded it on exit, on every decision whose own choose_key
  did not consult the optimizer (38-46 s each in the replay);
- each periodic character dump dropped the memo although it re-derived the
  same constants (decisions 18166, 18206);
- the memo signature held the obtainable ammunition by name, and the names
  carry the game's ``(N/shot N/turn)`` figures, which a fight in town moved
  (decision 18196).

Recorded: tests/fixtures/town-optimizer-memo-1111/ammo-18172-18196.json holds
the obtainable ammunition and the launchers of decisions 18172 and 18196 of
that replay (tests/extract_town_optimizer_memo_1111_fixture.py).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot.cli import _PolicyObserverScope, _capture_decision_facts
from hengbot.launcher_damage import best_obtainable_launcher_damage
from hengbot.model import (
    InventoryItem, PLAYER_CLASS_WARRIOR, Position, Snapshot, StoreItem, TVAL_SWORD,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_equipment import obtainable_ammunition_signature
from policy_fixtures import grid, item, player, seed_character_calibration


FIXTURE = (Path(__file__).with_name("fixtures") / "town-optimizer-memo-1111"
           / "ammo-18172-18196.json")


def town_board():
    sword = item("a", TVAL_SWORD, 1, name="dagger", known=True, fully_known=True,
                 is_equipment=True)
    return Snapshot(player(10, 10, class_id=PLAYER_CLASS_WARRIOR),
                    {Position(10, 10): grid(10, 10)}, [], floor_key=(0, 0, 0),
                    inventory=[sword], equipment=[])


class ObserverDefersOptimizerSearchTest(unittest.TestCase):
    def policy(self, board):
        policy = HengbotPolicy()
        seed_character_calibration(policy, board)
        policy._refresh_carried_equipment_catalog(board)
        return policy

    def test_observer_republishes_the_memo_instead_of_searching(self):
        board = town_board()
        policy = self.policy(board)
        with mock.patch("hengbot.policy_equipment.prepare_warrior_optimization",
                        return_value=mock.Mock(ready=False)) as prepare:
            with _PolicyObserverScope(policy):
                policy._prepare_equipment_optimization(board)
                self.assertEqual(
                    policy._equipment_optimization_telemetry["result_source"],
                    "observer-search-deferred")
            self.assertEqual(prepare.call_count, 0)
            # The decision path searches as before.
            policy._prepare_equipment_optimization(board)
            self.assertEqual(prepare.call_count, 1)
            self.assertEqual(policy._equipment_optimization_telemetry["result_source"],
                             "fresh-search")

    def test_decision_facts_never_run_the_search(self):
        board = town_board()
        policy = self.policy(board)
        with mock.patch("hengbot.policy_equipment.prepare_warrior_optimization",
                        return_value=mock.Mock(ready=False)) as prepare:
            facts = _capture_decision_facts(board, policy)
        self.assertEqual(prepare.call_count, 0)
        self.assertEqual(facts["equipment_optimization"]["result_source"],
                         "observer-search-deferred")
        self.assertIsNone(policy._equipment_optimization_signature)


class ObtainableAmmunitionSignatureRecordedTest(unittest.TestCase):
    @staticmethod
    def items(row):
        kinds = {"InventoryItem": InventoryItem, "StoreItem": StoreItem}
        out = []
        for data in row["ammunition"]:
            data = dict(data)
            kind = kinds[data.pop("_type")]
            data["known_flags"] = frozenset(data.get("known_flags") or ())
            out.append(kind(**{name: value for name, value in data.items()
                               if name in kind.__dataclass_fields__}))
        return out

    def test_shot_figures_in_the_names_leave_the_signature(self):
        rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual([row["decision_sequence"] for row in rows], [18172, 18196])
        before, after = (self.items(row) for row in rows)
        # The names moved (the memo key on main keyed them) ...
        self.assertNotEqual(sorted(each.name for each in before),
                            sorted(each.name for each in after))
        # ... what the optimizer reads did not.
        self.assertEqual(obtainable_ammunition_signature(before),
                         obtainable_ammunition_signature(after))
        for launcher in rows[1]["launchers"]:
            launcher = InventoryItem(**{
                name: (frozenset(value) if name == "known_flags" else value)
                for name, value in launcher.items()
                if name in InventoryItem.__dataclass_fields__})
            self.assertEqual(best_obtainable_launcher_damage(launcher, before),
                             best_obtainable_launcher_damage(launcher, after))


if __name__ == "__main__":
    unittest.main()
