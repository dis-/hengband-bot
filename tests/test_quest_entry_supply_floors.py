"""Every fixed quest's in-quest supply floor against its entry requirement (2026-11-27).

n1-c life-223 (tests/test_n1c_223_q25_restock_1127_recorded): Quest 25 was entered with the two
Healing potions its row asked and Word of Recall was read on phase 2's first board, none drunk --
the restock's floor (quest25_battle_hall ``HEALING_FLOOR`` 2) and the entry requirement
(``required_force.heal_potions`` lowered by ``over_match``) answered the same question apart.

The rule: a character that enters with exactly the entry requirement, nothing spent, does not leave
on a supply floor.  Asked here of every strategy file (strategy/quests) and every row a character can
be accepted on (the force, its ``force_alternatives``, its ``over_match``):

 * ``abort_conditions.recall_below_teleports`` (once_quest_recall ``below_scroll_floor``: fewer
   Teleportation scrolls than this): at or under every row's required count (``required_scrolls``,
   raised by ``teleport_scrolls_without_absorbed``);
 * Q25's ``HEALING_FLOOR`` (quest_entry_supply ``spent_to_floor``): entering with any row's count,
   nothing drunk, no leave; one drunk down to the floor, the leave.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import unittest
from pathlib import Path
from types import SimpleNamespace

from hengbot import quest25_battle_hall as hall, quest_entry_supply
from hengbot.quest_force_rows import ALTERNATIVES, OVER_MATCH, TELEPORT_SCROLLS_WITHOUT_ABSORBED
from hengbot.quest_strategies import load_quest_strategies

STRATEGIES = load_quest_strategies(Path(__file__).resolve().parents[1] / "strategy" / "quests")
FLOOR = (0, 48, 25)


def _rows(force: dict) -> list[dict]:
    """The force and every row merged over it (``force_alternatives``, ``over_match``)."""
    rows = [force, *({**force, **row} for row in force.get(ALTERNATIVES, ()))]
    rule = force.get(OVER_MATCH)
    if isinstance(rule, dict):
        rows += [{**row, "heal_potions": min(int(row.get("heal_potions", 0)), int(rule["heal_potions"]))}
                 for row in list(rows) if "heal_potions" in rule]
    return rows


def _entered(count: int):
    policy = SimpleNamespace(**{quest_entry_supply.STATE: (FLOOR, {quest_entry_supply.HEALING: count})})
    snapshot = SimpleNamespace(floor_key=FLOOR, in_town=False, quests={25: SimpleNamespace(fixed=True)})
    return policy, snapshot


class ScrollFloorTest(unittest.TestCase):

    def test_no_row_enters_below_its_recall_scroll_floor(self):
        checked = []
        for quest_id, profile in sorted(STRATEGIES.items()):
            floor = profile.abort_conditions.get("recall_below_teleports")
            if floor is None:
                continue
            force = profile.required_force
            for row in _rows(force):
                required = int(row.get("required_scrolls", {}).get("teleport", 0))
                for entry in {required, max(required, int(force.get(TELEPORT_SCROLLS_WITHOUT_ABSORBED, 0)))}:
                    checked.append(quest_id)
                    self.assertGreaterEqual(entry, int(floor), (quest_id, row.get("note"), entry, floor))
        self.assertEqual(sorted(set(checked)), [25, 33])


class HealingFloorTest(unittest.TestCase):

    def test_q25_entering_with_any_rows_count_does_not_leave(self):
        counts = sorted({int(row.get("heal_potions", 0)) for row in _rows(STRATEGIES[25].required_force)})
        self.assertEqual(counts, [2, 5])
        for count in counts:
            policy, snapshot = _entered(count)
            self.assertFalse(quest_entry_supply.spent_to_floor(
                policy, snapshot, quest_entry_supply.HEALING, count, hall.HEALING_FLOOR), count)
            drunk = min(count - 1, hall.HEALING_FLOOR)
            self.assertTrue(quest_entry_supply.spent_to_floor(
                policy, snapshot, quest_entry_supply.HEALING, drunk, hall.HEALING_FLOOR), count)

    def test_above_the_floor_no_leave_whatever_was_drunk(self):
        policy, snapshot = _entered(5)
        self.assertFalse(quest_entry_supply.spent_to_floor(
            policy, snapshot, quest_entry_supply.HEALING, hall.HEALING_FLOOR + 1, hall.HEALING_FLOOR))

    def test_no_record_the_first_count_stands_for_the_entry(self):
        policy, snapshot = _entered(2)
        delattr(policy, quest_entry_supply.STATE)
        snapshot.inventory = ()
        policy._exact_potion_count = lambda _snapshot, _sval: 2
        self.assertEqual(quest_entry_supply.entered_with(policy, snapshot, quest_entry_supply.HEALING), 2)
        self.assertEqual(getattr(policy, quest_entry_supply.STATE), (FLOOR, {quest_entry_supply.HEALING: 2}))
        self.assertFalse(quest_entry_supply.spent_to_floor(
            policy, snapshot, quest_entry_supply.HEALING, 2, hall.HEALING_FLOOR))


if __name__ == "__main__":
    unittest.main()
