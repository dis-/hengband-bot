"""n1-c life-113 2026-11-03 01:34/01:35 stall:town:restore-combat-weapon (x2).

The Magic-Eater wore 穴掘りのドワーフのつるはし {Q34} in the off hand beside
a main-hand サーベル, with 19 items in the pack.  The combat-weapon
restore saw a worn digger, its takeoff of the off-hand digger was refused
by the town pack budget (``town-pack-budget``), and the fallback wielded
the first pack weapon into the main hand (``wna``): タルワール went on,
サーベル into the pack, and the next board swapped them back, until the
stall watchdog stopped the bot; the restarted process did the same.

Pinned through the public choose_key: with a combat weapon in the main
hand the restore leaves the loadout as it is when the takeoff is refused,
and the board's key goes through the production executor.
Fixture: tests/extract_n1c_offhand_digger_1103_fixture.py.
DECLARED RECONSTRUCTED: the staff sequence record is the 01:23 capture's
(the stop's was not captured), with the absorbed staffs of every stage
(DECLARED CONSTRUCTED): the live sequence yielded these boards (their
town-work chain reaches _decide's restore rung), the replayed one would
approach the Magic shop instead.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_capability
from hengbot import me_staff_sequence as sequence
from tests.test_me_nokey_1031_recorded import PostedKey
from test_hourly_0700_1102_recorded import RecordedTownPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-offhand-digger-1103.json.gz"
DIGGER = "穴掘りのドワーフのつるはし (1d4) (+10,+5) (+6) {+掘|酸, Q34}"


def _case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class OffHandDiggerRestoreTest(RecordedTownPolicy, PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.case = _case()

    def policy(self):
        case = self.case
        policy = self.primed(case["boards"][0], [], case["skill"])
        record = sequence.state(policy)
        record.absorbed = dict(case["sequence"]["absorbed"])
        for stage in sequence.STAGES:
            for sval in stage.svals:
                record.absorbed.setdefault(me_capability.record_key("staff", sval), 10)
        record.powers_read = True
        return policy

    def test_recorded_swaps(self):
        rows = self.case["decisions"]
        self.assertEqual({(row["reason"], row["key"]) for row in rows},
                         {("town:restore-combat-weapon", "wna")})
        mains = []
        for raw in self.case["boards"]:
            worn = {item["slot"]: item["name"] for item in raw["equipment"]}
            self.assertEqual(worn["sub_hand"], DIGGER)
            mains.append(worn["main_hand"].split()[0])
            self.assertEqual(len(raw["inventory"]), 19)
        self.assertEqual(mains, ["サーベル", "タルワール"] * 2 + ["サーベル"])

    def test_refused_takeoff_beside_a_main_hand_weapon_wields_nothing(self):
        policy = self.policy()
        for raw in self.case["boards"]:
            key = policy.choose_key(self.board(policy, raw))
            self.assertNotEqual(key, "wna", raw["turn"])
            self.assertNotEqual(policy.last_reason, "town:restore-combat-weapon", raw["turn"])
            policy.confirm_key_posted(key)
        policy = self.policy()
        raw = self.case["boards"][0]
        self.post(policy, raw, policy.choose_key(self.board(policy, raw)))


if __name__ == "__main__":
    unittest.main()
