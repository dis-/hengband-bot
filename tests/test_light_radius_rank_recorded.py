"""Among permanent lights the wider light radius wins (issue #86 part 2).

USER DECISION 2026-10-19 「照らせる範囲も比べる」: compare the radius of
permanent (fuel-free) lights; other abilities stay under the equipment
comparison.  Observation 2026-10-03 「明確に下位互換の光源を装備している」: the
worn フェアノールのランプ (LITE_2, radius 2) tied the Home ★知識の石 /
★ガラドリエルの玻璃瓶 (LITE_3, radius 3) because light_source_quality ranks
every permanent light as 2.

The board is the #86 fixture (tests/fixtures/optimizer-lamp-20261019.jsonl.gz,
rows 0-4: c4a-loops-20261016/20261019-111025-no-key-exhausted, town, turn
1068217).

DECLARED CONSTRUCTED:
  - the character calibration (as in test_optimizer_lamp_recorded);
  - the Home lamp row (Home list item 28) worn in the light slot in place of
    the 0-turn torch, and removed from the Home list;
  - in its Home position the ★知識の石 row of the 10-03 capture
    (live-logs-20261003-1215/bot-state-fixed.jsonl, last ~9 Home list, Home
    slot 101), copied below as STONE_OF_LORE with only the slot renumbered.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import json
import unittest

from hengbot import equipment_optimizer
from hengbot.equipment_optimizer import OwnedEquipment
from hengbot.model import StoreItem
import test_optimizer_lamp_recorded as lamp_recorded
from test_optimizer_lamp_recorded import LAMP_NAME, TRAVEL_HOME


# ★知識の石 {明} of the 10-03 Home list: fully known, LITE_3 (123), IGNORE_*.
STONE_OF_LORE = {
    "ac": 0, "aware": True, "charges": 0, "charging": False, "count": 1,
    "damage_dice": {"num": 0, "sides": 0}, "fully_known": True,
    "inscription": "", "is_artifact": True, "is_bounty": False,
    "is_broken": False, "is_cursed": False, "is_ego": False,
    "is_equipment": True, "known": True,
    "known_flags": [84, 85, 86, 87, 88, 123], "name": "★知識の石 {明}",
    "pval": 0, "slot": 101, "sval": 7, "to_a": 0, "to_d": 0, "to_h": 0,
    "tval": 39, "weight": 15,
}
# ★ガラドリエルの玻璃瓶 of the same 10-03 Home list (Home slot 100): LITE_3 and
# +1 searching (flag 9, pval 1).
PHIAL = {
    "ac": 0, "aware": True, "charges": 1, "charging": False, "count": 1,
    "damage_dice": {"num": 0, "sides": 0}, "fully_known": True,
    "inscription": "!!", "is_artifact": True, "is_bounty": False,
    "is_broken": False, "is_cursed": False, "is_ego": False,
    "is_equipment": True, "known": True,
    "known_flags": [9, 84, 85, 86, 87, 88, 123],
    "name": "★ガラドリエルの玻璃瓶 (+1探索) {+探;明, !!}",
    "pval": 1, "slot": 100, "sval": 4, "to_a": 0, "to_d": 0, "to_h": 0,
    "tval": 39, "weight": 10,
}
WORN_LAMP = "equipped:ff2b3ffaa208a881:0"
TR_LITE_1 = 77
TR_LITE_2 = 122
TR_LITE_3 = 123
TR_LITE_M1 = 124
TR_DARK_SOURCE = 146


class LightRadiusRankRecordedTest(lamp_recorded.OptimizerLampRecordedTest):
    # Re-run none of the inherited #86 tests here; they stay in their module.
    test_fixture_is_the_recorded_town_board_and_home_list = None
    test_recorded_town_board_withdraws_the_home_lamp = None
    test_worn_lantern_withdraws_the_home_lamp_before_departure = None
    test_control_without_the_lamp_the_infravision_torch_is_withdrawn = None
    test_control_without_the_lamp_the_worn_lantern_is_kept = None

    def _lamp_worn_rows(self, home_light, worn_lamp_extra_flags=()):
        rows = [json.loads(line) for line in self.lines[:5]]
        home_rows = [
            row for row in rows
            if row.get("knowledge", {}).get("category") == "home"
        ]
        lamp = next(
            item for item in home_rows[0]["knowledge"]["items"]
            if item.get("name") == LAMP_NAME
        )
        for row in rows:
            if row.get("type") == "player_turn":
                row["equipment"] = [
                    dict(
                        lamp,
                        slot="light",
                        known_flags=sorted(
                            set(lamp["known_flags"]) | set(worn_lamp_extra_flags)
                        ),
                    )
                    if item["slot"] == "light" else item
                    for item in row["equipment"]
                ]
            if row in home_rows:
                row["knowledge"]["items"] = [
                    dict(home_light, slot=item["slot"])
                    if item.get("name") == LAMP_NAME else item
                    for item in row["knowledge"]["items"]
                ]
        return [json.dumps(row, ensure_ascii=False) for row in rows]

    def _stone_id(self):
        return next(
            item.id for item in self.policy._equipment_catalog.items
            if item.item.name == STONE_OF_LORE["name"]
        )

    def test_worn_lamp_is_replaced_by_the_radius_3_home_artifact_light(self):
        decisions = self._replay(self._lamp_worn_rows(STONE_OF_LORE))
        # 30d4bba7: ('\x1b`n%.', 'shop:travel'), no equipment transaction;
        # the lamp (radius 2) and the stone (radius 3) both rank 2 and the
        # worn set wins the tie.
        self.assertEqual(decisions[-1], TRAVEL_HOME)
        stone = self._stone_id()
        self.assertEqual(
            self._transaction_actions(),
            [
                ("withdraw", stone, None),
                ("takeoff", WORN_LAMP, "light"),
                ("equip", stone, "light"),
                ("deposit", WORN_LAMP, None),
            ],
        )

    def test_worn_lamp_is_replaced_by_the_home_phial(self):
        # 30d4bba7: ('\x1b`n%.', 'shop:travel'), no equipment transaction.
        decisions = self._replay(self._lamp_worn_rows(PHIAL))
        self.assertEqual(decisions[-1], TRAVEL_HOME)
        phial = next(
            item.id for item in self.policy._equipment_catalog.items
            if item.item.name == PHIAL["name"]
        )
        self.assertEqual(
            self._transaction_actions(),
            [
                ("withdraw", phial, None),
                ("takeoff", WORN_LAMP, "light"),
                ("equip", phial, "light"),
                ("deposit", WORN_LAMP, None),
            ],
        )

    def test_control_radius_does_not_override_a_survival_difference(self):
        # DECLARED CONSTRUCTED: the worn lamp also resists chaos (TR_RES_CHAOS
        # 62).  The radius-3 stone lacks it, so the modeled survival differs
        # and the radius never enters the comparison: the lamp stays worn.
        decisions = self._replay(
            self._lamp_worn_rows(STONE_OF_LORE, worn_lamp_extra_flags=(62,))
        )
        self.assertNotEqual(decisions[-1][1], TRAVEL_HOME[1])
        self.assertIsNone(self._transaction_actions())

    def test_control_unidentified_artifact_light_does_not_reveal_its_radius(self):
        # The same stone before full identification: its LITE_3 is not known
        # to the player, so it does not outrank the known radius-2 lamp.
        unknown = dict(
            STONE_OF_LORE,
            fully_known=False,
            known_flags=[],
            name="知識の石",
        )
        decisions = self._replay(self._lamp_worn_rows(unknown))
        self.assertNotEqual(decisions[-1][1], TRAVEL_HOME[1])
        self.assertIsNone(self._transaction_actions())

    def test_control_lamp_worn_with_only_fuel_lights_at_home_is_kept(self):
        # Lamp vs lantern vs torch ordering is unchanged: with the lamp worn,
        # the Home torches and the empty pack lantern do not
        # displace it.
        rows = self._lamp_worn_rows(STONE_OF_LORE)
        rows = [json.loads(line) for line in rows]
        for row in rows:
            if row.get("knowledge", {}).get("category") == "home":
                row["knowledge"]["items"] = [
                    item for item in row["knowledge"]["items"]
                    if item.get("name") != STONE_OF_LORE["name"]
                ]
        decisions = self._replay(
            [json.dumps(row, ensure_ascii=False) for row in rows]
        )
        self.assertNotEqual(decisions[-1][1], TRAVEL_HOME[1])
        self.assertIsNone(self._transaction_actions())
        self.assertEqual(
            self._catalog_light(WORN_LAMP).item.name, LAMP_NAME
        )


def _owned(tval, sval, flags):
    return OwnedEquipment(
        id="test:light",
        item=StoreItem(
            letter="a", name="light", count=1, tval=tval, sval=sval,
            price=0, fully_known=True, known_flags=frozenset(flags),
        ),
        origin="home",
    )


def _radius(item):
    return equipment_optimizer.permanent_light_radius(item)


class PermanentLightRadiusTest(unittest.TestCase):
    def test_radius_is_the_game_sum_of_the_known_light_flags(self):
        self.assertEqual(_radius(_owned(39, 2, [TR_LITE_2])), 2)
        self.assertEqual(_radius(_owned(39, 4, [TR_LITE_3])), 3)
        self.assertEqual(
            _radius(_owned(39, 7, [TR_LITE_3, TR_LITE_M1])), 2
        )
        self.assertEqual(
            _radius(
                _owned(39, 7, [TR_LITE_1, TR_LITE_3, TR_DARK_SOURCE])
            ),
            0,
        )
        self.assertEqual(
            _radius(_owned(39, 7, [TR_LITE_M1, TR_DARK_SOURCE])),
            -1,
        )

    def test_fuel_lights_and_non_lights_have_no_permanent_radius(self):
        self.assertEqual(_radius(None), 0)
        self.assertEqual(_radius(_owned(39, 0, [TR_LITE_1])), 0)
        self.assertEqual(_radius(_owned(39, 1, [TR_LITE_2])), 0)
        # A weapon (tval 23, sval 7) with a light flag is not a light.
        self.assertEqual(_radius(_owned(23, 7, [TR_LITE_1])), 0)


if __name__ == "__main__":
    unittest.main()
