"""D45, second scene: the emptied hand goes back before a flight it causes,
and on a return that will not wield the digger; an unreachable monster holds
no flee:wait.

Recorded: n1-a life-518 (warrior Lv8, Yeek cave 1F, mining for funds;
2026-11-12, three loop stops 18:04-18:06).  'ta' (take off the Broad Sword,
fundraise:wield-digging-tool) at game turn 139869; a white worm mass (race 31,
Lv1) came into view three cells away at 139876 and the flee rung answered
first (the empty hand's free damage of 0 reads it T1), so the re-arm
(mining_loadout.rollback_key) yielded; Teleportation scrolls followed and the
return walked bare-handed from 139938 (fundraise:seek-upstairs-explore,
nothing in view) on; from 156220 to the livelock stop at 156613 it waited
(flee:wait) seven cells from a grey mold (race 20, NEVER_MOVE, no ranged
attack).  The boards, the skill row, the decision rows and the race rows are
frozen in tests/fixtures/mining-bare-hands-20261112.json.gz
(tests/extract_mining_bare_hands_1112_fixture.py).  Every decision goes
through the public ``choose_key`` and every posted key through the
production executor.

DECLARED RECONSTRUCTED: the mining-run state (mode "mine", one planned run,
the detection read on this floor, the quiet streak that admitted the
recorded strip) and, on the 139938 and 156598 boards, the latched return
(``_returning_to_town``: the recorded reasons are the floor exit's).
DECLARED CONSTRUCTED: the executor's replies (the posted wield or takeoff
applied to the board, the pack relettered, ten game turns later); the low-HP
control (the recorded 139876 board at 30% HP); the
walk-out dig control (``_breakout_dig_floor`` set to the board's floor, as
walkout_dig.dig_step_key sets it when it strips); the no-digger mold board
(the recorded 156598 board with both diggers taken out of the pack).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
import string
import unittest

from hengbot.cli import _ExecutorInputPort, SendResult, _transport_key
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import MINING_THREAT_FREE_LIMIT
from tests.support import recorded as harness
from tests.support.recorded import FaithfulHookGame, command_screen, prompt_screen


FIXTURE = Path(__file__).with_name("fixtures") / "mining-bare-hands-20261112.json.gz"
SWORD, SHOVEL, PICK = "ブロード・ソード", "シャベル", "つるはし"
WORM_MASS, GREY_MOLD = 31, 20
STRIP = "fundraise:wield-digging-tool"
# hengbot.mining_loadout.REARM_REASON, spelled out so the revert check runs
# every test instead of an import error.
REARM_REASON = "melee:rearm-empty-hand"
ITEM_PROMPTS = {"w": "(Inven: a-n, ESC) どれを装備しますか?",
                "t": "(Equip: a-l, ESC) どれを装備からはずしますか?"}


def letter_of(raw, prefix):
    return next(item["slot"] for item in raw["inventory"] if item["name"].startswith(prefix))


def reletter(raw):
    for letter, item in zip(string.ascii_lowercase, raw["inventory"]):
        item["slot"] = letter
    return raw


def wielded(raw, prefix, slot):
    """The board after the pack item named ``prefix`` went into ``slot``."""
    after = copy.deepcopy(raw)
    item = next(i for i in after["inventory"] if i["name"].startswith(prefix))
    after["inventory"].remove(item)
    after["equipment"] = [i for i in after["equipment"] if i["slot"] != slot]
    after["equipment"].append(dict(item, slot=slot))
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def taken_off(raw, slot):
    after = copy.deepcopy(raw)
    item = next(i for i in after["equipment"] if i["slot"] == slot)
    after["equipment"].remove(item)
    after["inventory"].append(dict(item, slot="?"))
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def bare_hands(raw):
    return not any(item["slot"] in ("main_hand", "sub_hand") for item in raw["equipment"])


class MiningBareHandsRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        cls.races = {}
        for key, facts in cls.case["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            cls.races[int(key)] = MonraceKnowledge(**facts)

    def board(self, name):
        return copy.deepcopy(self.case["boards"][name])

    def policy(self, raw, *, returning=False):
        policy = ConservativePolicy(monrace_knowledge=dict(self.races))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy.prime(board)
        policy.consume_skill_knowledge(copy.deepcopy(self.case["knowledge"]))
        # DECLARED RECONSTRUCTED (module docstring).
        policy._fundraising_mode = "mine"
        policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
        policy._mining_scroll_used_floor = board.floor_key
        policy._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
        policy._returning_to_town = returning
        return policy

    @staticmethod
    def decide(policy, raw):
        return str(policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))

    def post(self, policy, raw, key, following):
        # cmd-equipment.cpp do_cmd_wield / do_cmd_takeoff open the item
        # source prompt; the hand chain needs no follow-up on these boards.
        prompts = [prompt_screen(ITEM_PROMPTS[key[0]])] if key[0] in ITEM_PROMPTS else []
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = prompts + [command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in prompts] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        self.assertTrue(policy.confirm_key_posted(key))

    def rearm(self, policy, raw):
        """The decision re-arms the Broad Sword; the armed board it posts to."""
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("w" + letter_of(raw, SWORD), REARM_REASON))
        armed = wielded(raw, SWORD, "main_hand")
        self.post(policy, raw, key, armed)
        return armed

    def test_capture_pins_the_recorded_scene(self):
        decisions = self.case["decisions"]
        recorded = {turn: [(row["reason"], row["key"]) for row in rows]
                    for turn, rows in decisions.items()}
        self.assertEqual(recorded, {
            "139869": [(STRIP, "ta")],
            "139876": [("flee", "3")],
            "139938": [("fundraise:seek-upstairs-explore", "7")],
            "156598": [("flee:wait", "5")],
        })
        self.assertEqual(decisions["139869"][0]["fundraising"]["mode"], "mine")
        worn = self.board("worn")
        self.assertEqual([item["name"][:len(SWORD)] for item in worn["equipment"]
                          if item["slot"] == "main_hand"], [SWORD])
        self.assertEqual(worn["visible_monsters"], [])
        for name in ("sighted", "returning", "mold"):
            raw = self.board(name)
            self.assertTrue(bare_hands(raw), name)
            self.assertTrue(letter_of(raw, SWORD) and letter_of(raw, SHOVEL) and letter_of(raw, PICK))
        self.assertEqual({m["race_id"] for m in self.board("sighted")["visible_monsters"]},
                         {WORM_MASS})
        self.assertEqual(self.board("returning")["visible_monsters"], [])
        self.assertEqual({m["race_id"] for m in self.board("mold")["visible_monsters"]},
                         {GREY_MOLD})
        self.assertIn("NEVER_MOVE", self.races[GREY_MOLD].flags)
        self.assertEqual(self.races[GREY_MOLD].level, 1)

    def test_strip_interrupted_rearms_before_the_flight_the_empty_hand_causes(self):
        # The recorded chain: the strip at 139869, the worm mass three cells
        # away at 139876 (recorded: flee).
        worn, sighted = self.board("worn"), self.board("sighted")
        policy = self.policy(worn)
        key = self.decide(policy, worn)
        self.assertEqual((key, policy.last_reason), ("ta", STRIP))
        self.post(policy, worn, key, taken_off(worn, "main_hand"))
        armed = self.rearm(policy, sighted)
        key = self.decide(policy, armed)
        self.assertFalse(policy.last_reason.startswith(("flee", "melee:rearm")),
                         (key, policy.last_reason))
        self.assertFalse(key.startswith(("w", "t", "r")), (key, policy.last_reason))

    def test_flight_still_first_at_low_hp(self):
        # DECLARED CONSTRUCTED: the recorded 139876 board at 30% HP.
        low = self.board("sighted")
        low["player"]["hp"] = low["player"]["max_hp"] * 3 // 10
        policy = self.policy(low)
        key = self.decide(policy, low)
        self.assertNotEqual(policy.last_reason, REARM_REASON, key)
        self.assertTrue(policy.last_reason.startswith("flee"), (key, policy.last_reason))

    def test_return_rearms_with_nothing_in_view(self):
        # Recorded 139938: the return walked bare-handed (seek-upstairs-explore).
        raw = self.board("returning")
        policy = self.policy(raw, returning=True)
        armed = self.rearm(policy, raw)
        key = self.decide(policy, armed)
        self.assertTrue(policy.last_reason.startswith("fundraise:seek-upstairs"),
                        (key, policy.last_reason))

    def test_controls_where_the_digger_is_still_wanted(self):
        raw = self.board("returning")
        # The run going on continues the swap with the digger.
        policy = self.policy(raw)
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("w" + letter_of(raw, SHOVEL), STRIP))
        # A walk-out dig that stripped on this floor keeps its swap (DECLARED CONSTRUCTED).
        # The breakout's restore rung clears the mark once no dig route is
        # left, so the rung itself is asked on this board.
        policy = self.policy(raw, returning=True)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        policy._breakout_dig_floor = snapshot.floor_key
        self.assertIsNone(policy._mining_loadout_rollback_key(snapshot))

    def test_unreachable_grey_mold_holds_no_flee_wait(self):
        # Recorded 156598: flee:wait seven cells from the grey mold.
        raw = self.board("mold")
        policy = self.policy(raw, returning=True)
        armed = self.rearm(policy, raw)
        key = self.decide(policy, armed)
        self.assertFalse(policy.last_reason.startswith("flee"), (key, policy.last_reason))
        # Without a digger the re-arm does not apply; the mold still holds no
        # flight (DECLARED CONSTRUCTED: both diggers out of the pack).
        bare = self.board("mold")
        bare["inventory"] = [item for item in bare["inventory"]
                             if not item["name"].startswith((SHOVEL, PICK))]
        bare = reletter(bare)
        policy = self.policy(bare, returning=True)
        key = self.decide(policy, bare)
        self.assertFalse(policy.last_reason.startswith("flee"), (key, policy.last_reason))
        self.assertNotEqual(key, "5")


if __name__ == "__main__":
    unittest.main()
