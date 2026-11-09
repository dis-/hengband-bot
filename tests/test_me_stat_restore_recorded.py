"""#47 n1-c life-096: a drained stat is restored from a fundraising visit's shelf.

Owner 2026-11-01 (on the dual wield at STR 6): 「腕力の回復だけ直す」 -- keep the
optimizer's AC 100 comparison; fix only that the bot never bought or drank
Restore Strength while STR was drained.

Recorded (build bot-e69085962 line, n1-c life-096, zombie Magic-Eater Lv11):
STR 18/31 was drained to 6 by a Red Jelly and giant red ants.  The Alchemist
sold 腕力復活の薬 within the gold on every visit, yet the fundraising branch of
_legacy_next_purchase_unreserved (modes prepare / mine) listed only the mining
kit and the recall scroll and returned None, so the restore potion was never
reached: decision 92 '\\x1b' shop:in-store-done after the recall purchase
(turn 1462282, mode prepare), decision 610 '\\x1b' shop:observe-and-leave
(turn 1645367, mode mine, "observed-page-nothing-wanted").

Each case starts on the recorded Alchemist page; every decision goes through
the public chooser and every posted key through the production executor
(the store harness of test_lv7_town_stop_recorded / test_me_town_stops_recorded).

DECLARED RECONSTRUCTED: the fundraising mode of the recorded decision rows;
the Magic-Eater staff record of the death capture (its absorbed powers, which
count as the treasure detection the kit wants); the staff power list read.
DECLARED CONSTRUCTED: the game's reply to every posted key (the bought
potion in the pack, ten game turns later; the quaff restoring the stat).

Fixture: tests/extract_me_stat_restore_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path

from hengbot import me_staff_sequence
from hengbot.model import parse_snapshot
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_town_stops_recorded as me_town
import tests.support.recorded as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "me-stat-restore-20261101.json.gz"
FIXTURE_SHA256 = "ed1365133fcabf84546f3ebf27b10852358e0d894d1b0c9ce107f98c731a418c"
RESTORE_STR = "腕力復活の薬"
QUAFF_STR = "restore:quaff-str"
STOPS = me_town.STOPS


class MagicEaterStatRestoreRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    store_reply = me_town.MagicEaterTownStopsRecordedTest.reply
    lv7_post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        lv7.Lv7TownStopRecordedTest.setUpClass()
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.document = json.load(stream)

    def boundary(self, name):
        case = self.document["cases"][name]
        mode = case["recorded"][-1]["fundraising"]["mode"]
        policy, raw = lv7.Lv7TownStopRecordedTest().boundary(dict(
            monraces=case["monraces"], snapshot=case["board"], knowledge=case["knowledge"],
            state={"modes_and_latches": {}}))
        # DECLARED RECONSTRUCTED (module docstring).
        policy._fundraising_mode = mode
        record = me_staff_sequence.state(policy)
        saved = self.document["me_staff_sequence"]
        record.absorbed = {int(sval): count for sval, count in saved["absorbed"].items()}
        record.stage, record.remaining, record.powers_read = (
            saved["stage"], list(saved["remaining"]), True)
        return policy, raw

    def post(self, policy, raw, key, following):
        if key.startswith("q"):
            # cmd-item/cmd-quaff.cpp do_cmd_quaff_potion opens the item prompt.
            game = executor_harness.FaithfulHookGame()
            game.state = copy.deepcopy(raw)
            game.screen = executor_harness.command_screen(raw["turn"])
            game.screens = [executor_harness.prompt_screen("(Inven: a-w, ESC) どの薬を飲みますか?"),
                            executor_harness.command_screen(following["turn"])]
            game.states = [copy.deepcopy(raw), copy.deepcopy(following)]
            _, _, executor = self.make(game)
            self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
            from hengbot.cli import _ExecutorInputPort, SendResult
            port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
            self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                                "sequence": policy._decision_sequence}),
                             SendResult.SENT, port.last_result.reason)
            self.assertEqual(port.last_result.outcome, "completed")
            self.assertEqual(game.accepted, ["q", key[1:]])
            policy.confirm_key_posted(key)
            return
        self.lv7_post(policy, raw, key, following)

    def reply(self, policy, raw, key, case):
        """DECLARED CONSTRUCTED: the engine's reply to the posted key."""
        if key.startswith("q"):
            following = copy.deepcopy(raw)
            following["turn"] += 10
            following["messages"] = []
            potion = next(it for it in following["inventory"] if it["slot"] == key[1])
            potion["count"] -= 1
            following["inventory"] = [it for it in following["inventory"] if it["count"]]
            self.quaffed.append(potion["name"])
            # quaff-effects.cpp SV_POTION_RES_STR: do_res_stat(A_STR).
            strength = following["player"]["stats"]["str"]
            strength.update(drained=False, use=strength["top"])
            return following
        return self.store_reply(policy, raw, key, case)

    def drive(self, name, *, limit):
        case = self.document["cases"][name]
        policy, raw = self.boundary(name)
        self.pages = copy.deepcopy(case["pages"])
        self.bought, self.quaffed, reasons = [], [], []
        for _ in range(limit):
            key = str(policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge)))
            reasons.append(policy.last_reason)
            if self.quaffed:
                return policy, raw, reasons
            self.assertNotEqual(key, "", reasons[-8:])
            self.assertFalse(policy.last_reason.startswith(STOPS), reasons[-8:])
            following = self.reply(policy, raw, key, case)
            self.post(policy, raw, key, following)
            raw = following
        self.fail(("no restore", self.bought, reasons[-12:]))

    def test_capture_pins_the_unrestored_strength(self):
        for name, expected in (("prepare", ("\x1b", "shop:in-store-done", "prepare")),
                               ("mine", ("\x1b", "shop:observe-and-leave", "mine"))):
            with self.subTest(case=name):
                case = self.document["cases"][name]
                last = case["recorded"][-1]
                self.assertEqual((last["key"], last["reason"], last["fundraising"]["mode"]), expected)
                board = case["board"]
                strength = board["player"]["stats"]["str"]
                self.assertTrue(strength["drained"])
                self.assertLess(strength["use"], strength["top"])
                ware = next(item for item in board["store"]["items"]
                            if item["name"].startswith(RESTORE_STR))
                self.assertLessEqual(ware["price"], board["player"]["gold"])
        self.assertEqual(self.document["cases"]["mine"]["recorded"][-1]["shop_selector"]
                         ["rejection_reason"], "observed-page-nothing-wanted")

    def test_fundraising_visit_buys_and_drinks_the_restore_potion(self):
        for name in ("prepare", "mine"):
            with self.subTest(case=name):
                _policy, _raw, reasons = self.drive(name, limit=40)
                self.assertEqual([item for item, _ in self.bought
                                  if item.startswith(RESTORE_STR)][:1],
                                 [next(item["name"] for item in self.document["cases"][name]
                                       ["board"]["store"]["items"]
                                       if item["name"].startswith(RESTORE_STR))])
                self.assertEqual(reasons[-2], QUAFF_STR)
                self.assertTrue(self.quaffed[0].startswith(RESTORE_STR))


if __name__ == "__main__":
    import unittest
    unittest.main()
