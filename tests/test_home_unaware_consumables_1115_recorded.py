"""Unaware potions and scrolls are identified with the carried means (n1-b life-405, n1-c life-214, 2026-11-15).

Owner 2026-11-15 「自宅に未鑑定の薬と巻物を溜め込む問題が改善されていない」: both viewing
Magic-Eaters' Homes held unaware flavours (紺碧の薬 x2, 赤銅色の薬 x4, 橙色の薬 and a dozen
「…」と書かれた巻物) while each held the absorbed Identify (and the Home 20+ Identify scrolls).
Answer: 「鑑定の手段で調べる」 - identify them with the character's means (an Identify scroll,
the Identify staff or rod, the absorbed Identify), then keep, sell or destroy the now-known kind
by the existing rules; with no means leave them as they are (no sale to learn them, no trial use).

Before: no identification owner took an unaware potion or scroll.  From 20F
(``protected_unknown_consumable``) a carried one was shelved at Home, and the Home's
identification take (``_bind_catalogued_home_identification_withdrawal``) served equipment and
devices only, so the shelf only grew.

Now ``_unaware_consumable_awaits_identification`` makes them identification-flow work (from
20F, where ``_find_low_level_sale`` no longer sells them as they are), and one answer,
``_unaware_consumable_identifiable_now``, decides whether a carried means identifies one now:

* carried: ``_town_device_processing_key`` identifies it (``_carried_identify_command``); with no
  means the waiting deposit shelves it and no source is bought for it;
* at Home: the junk sweep takes the stack in the relief's identify mode
  (``item_fate.sweep_identify_ware``, before a sale ware), identifies it, and ends its entry over
  the known stack, which the existing rules then handle.

Recorded (choose_key on the town-arrival checkpoints, tests/extract_home_unaware_consumables_1115_
fixture.py):

* n1-b life-405 23:21:22: rows 0-1 decide as recorded; on row 2 the carried
  「毒全 翔完 進事」と書かれた巻物 is identified with the absorbed Identify, where the recorded
  visit walked Home and shelved it (row 19 home:atomic-deposit).
* n1-c life-214 23:39:29: rows 0-2 decide as recorded (the sweep starts on the Home page); on
  row 3 the sweep takes the two 紺碧の薬 instead of the recorded sale take of a ring.

DECLARED CONSTRUCTED (n1-c): the outside board after the take is row 4's recorded board with the
pack the take gives (the recorded taken ring left out, the two 紺碧の薬 carried as the fourth
row, as an unaware potion sorts after the aware ones); the board after the identification shows
them as 眠りの薬 (the identity the replay cannot know).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.model import SV_POTION_SLEEP, TVAL_POTION, TVAL_SCROLL, StoreItem, parse_snapshot
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load

ROOT = Path(__file__).with_name("fixtures") / "home-unaware-consumables-1115"
SLOTS = "abcdefghijklmnopqrstuvw"


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return key, policy.last_reason


def raw(row):
    return json.loads(row["line"] if row["line"] is not None else row["inputs"][-1])


class HomeUnawareConsumables1115RecordedTest(unittest.TestCase):
    def replay(self, name, fixed_row):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, recorded, steps = load(ROOT / name, Path(scratch.name))
        for index, (row, supply) in enumerate(steps[:fixed_row]):
            self.assertEqual(decide(policy, supply()), (row["key"], row["reason"]), index)
        return policy, recorded, steps

    def test_n1b_405_carried_unaware_scroll_is_identified_with_the_absorbed_power(self):
        policy, recorded, steps = self.replay("n1b405", 2)
        self.assertEqual(recorded[2]["reason"], "equipment-transaction:travel-home")
        board = steps[2][1]()
        scroll = next(item for item in board.inventory
                      if item.tval == TVAL_SCROLL and not item.aware)
        self.assertGreaterEqual(policy._deepest_level, 20)

        key, reason = decide(policy, board)

        self.assertEqual(reason, "identify:device")
        # The absorbed Identify's power key, then the scroll's pack letter.
        self.assertTrue(key.startswith("mA"), key)
        self.assertEqual(key[-1], scroll.slot)
        self.assertTrue(policy._unaware_consumable_awaits_identification(scroll))

    def test_n1c_214_home_sweep_takes_identifies_and_releases_the_unaware_potion(self):
        policy, recorded, steps = self.replay("n1c214", 3)
        self.assertEqual(recorded[3]["reason"], "home-errand:atomic-withdraw:full-home-sale")

        key, reason = decide(policy, steps[3][1]())

        self.assertEqual(reason, "home-errand:atomic-withdraw:full-home-discard")
        relief = policy._home_full_relief
        self.assertEqual(relief["mode"], "identify")
        self.assertEqual(relief["sale"][0], ("紺碧の薬", TVAL_POTION, -1))
        self.assertEqual(policy._home_errand.request.quantity, 2)
        self.assertNotEqual(key, recorded[3]["key"])

        # DECLARED CONSTRUCTED: the outside board after this take.
        before, after = raw(recorded[3]), raw(recorded[4])
        page = raw(recorded[2])
        ware = next(item for item in page["store"]["items"] if item["name"] == "紺碧の薬")
        potion = dict(copy.deepcopy(before["inventory"][0]), name=ware["name"], count=2,
                      aware=False, known=False, fully_known=False, pval=0, charges=0,
                      weight=ware["weight"])
        potion.pop("sval")
        inventory = copy.deepcopy(before["inventory"])
        inventory.insert(3, potion)
        for index, item in enumerate(inventory):
            item["slot"] = SLOTS[index]
        taken = dict(copy.deepcopy(after), inventory=inventory)
        key, reason = decide(policy, parse_snapshot(taken, policy._monrace_knowledge))
        self.assertEqual(reason, "identify:normal")
        self.assertTrue(key.startswith("mA"), key)
        self.assertEqual(key[-1], "d")

        # DECLARED CONSTRUCTED: the identification's effect.
        known = copy.deepcopy(taken)
        known["turn"] += 10
        known["inventory"][3].update(name="眠りの薬", sval=SV_POTION_SLEEP, aware=True, known=True)
        board = parse_snapshot(known, policy._monrace_knowledge)
        _key, reason = decide(policy, board)
        self.assertIsNone(policy._home_full_relief)
        self.assertFalse(reason.startswith("town:blocked:"), reason)
        sleep = next(item for item in board.inventory if item.sval == SV_POTION_SLEEP)
        self.assertFalse(policy._unaware_consumable_awaits_identification(sleep))

    def test_unaware_consumables_sold_as_they_are_stay_with_the_sale(self):
        """Shallower than 20F and after a scavenging run ``_find_low_level_sale`` sells them."""
        policy = HengbotPolicy()
        potion = StoreItem("a", "紺碧の薬", 2, TVAL_POTION, -1, 0, aware=False, known=False)
        policy._deepest_level = 19
        self.assertFalse(policy._unaware_consumable_awaits_identification(potion))
        policy._deepest_level = 20
        self.assertTrue(policy._unaware_consumable_awaits_identification(potion))
        policy._sell_scavenged_consumables = True
        self.assertFalse(policy._unaware_consumable_awaits_identification(potion))


if __name__ == "__main__":
    unittest.main()
