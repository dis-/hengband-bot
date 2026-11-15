"""A mining run's breeder fight re-arms and, with no way to the stairs, leaves by Recall (n1-a life-525).

n1-a life-525 (Lv37 Warrior, build 25d9cc382) stopped on Yeek cave 1F on 2026-11-15 16:54:06
(loop-detected) and, restarted on the same floor, again at 16:54:25.  Mining had put the two
diggers in its hands (穴掘りのドワーフのつるはし, 穴掘りの戦闘用つるはし) when a 巨大ハツカネズミ swarm
closed in.  From decision 2508 on, with mice beside it, the contact re-arm of the mining-combat
spec (_restore_mining_combat_hand_key after MINING_COMBAT_CONTACT_LIMIT contact decisions)
asked for the トライデント under the executor goal combat-loadout, and the executor refused it
(goal-already-superseded): the fight changed neither gold, experience nor items since the
mining-loadout post (equipment_mutation.progress_core).  The bot fought with the two diggers
for 87 decisions, 467 of 513 blows missing (the two-weapon penalty,
player-status.cpp calc_double_weapon_penalty).  From 2547 the floor was latched as a breeder
breakthrough; on a mining floor the latch's Recall is never read, and with no remembered route
to the up-stairs at (60,57) the breakthrough cleared a corridor the mice refilled toward a
frontier until the loop detector stopped it -- ten Recall scrolls carried.  After the restart
the trident was in hand (58 hits, 58 kills) and the corridor still refilled.

Fix: the contact re-arm undoes the mining swap, under mining_loadout.ROLLBACK_GOAL like the
empty-hand re-arm, so the supersession guard does not refuse it.

Recorded: the boards are the incident capture's (tests/extract_n1a_525_mouse_swarm_1115_fixture.py:
the town-arrival checkpoint replayed over the snapshot tail into the dungeon, all 741 decisions
matching the record; ``policy.pkl.xz`` is that policy before decision 2508), decided through the
public choose_key.  Where a test walks on past a board the fix decides differently, the recorded
key is posted (FORCED).

DECLARED CONSTRUCTED: the boards after the re-arm's wield and takeoff are 2508's board with
the trident in the main hand (and the off-hand digger in the pack), the turn advanced.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import re
import string
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import SendResult, _ExecutorInputPort, _consume_response_sequence, _transport_key
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from tests.support import recorded as harness
from tests.support.recorded import FaithfulHookGame, command_screen, prompt_screen

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-mouse-swarm-1115"
TRIDENT, RECALL = "★顕聖二郎真君のトライデント", "帰還の詔の巻物"
MOUSE = 27
LATCH = 2547
REARM = "melee:restore-weapon"
# cmd-equipment.cpp do_cmd_takeoff's item prompt.  observed_input._compile_*: a bare
# 'w'/'t' + item waits for the item prompt; a hand answer after it ('wma', do_cmd_wield's
# "Equip which hand?" with both hands full) has no recorded chooser plan and is posted whole.
TAKEOFF_PROMPT = "(Equip: a-l, ESC) どれを装備からはずしますか?"
MISS, KILL = "かわされた", "葬り去った"


def reletter(raw):
    for letter, item in zip(string.ascii_lowercase, raw["inventory"]):
        item["slot"] = letter
    return raw


def wielded(raw, prefix, slot):
    """DECLARED CONSTRUCTED: the board after the pack item ``prefix`` went into ``slot``."""
    after = copy.deepcopy(raw)
    item = next(i for i in after["inventory"] if i["name"].startswith(prefix))
    after["inventory"].remove(item)
    displaced = [i for i in after["equipment"] if i["slot"] == slot]
    after["equipment"] = [i for i in after["equipment"] if i["slot"] != slot]
    after["equipment"].append(dict(item, slot=slot))
    after["inventory"].extend(dict(i, slot="?") for i in displaced)
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def taken_off(raw, slot):
    """DECLARED CONSTRUCTED: the board after ``slot`` was taken off into the pack."""
    after = copy.deepcopy(raw)
    item = next(i for i in after["equipment"] if i["slot"] == slot)
    after["equipment"].remove(item)
    after["inventory"].append(dict(item, slot="?"))
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def letter_of(raw, prefix):
    return next(item["slot"] for item in raw["inventory"] if item["name"].startswith(prefix))


class N1a525MouseSwarm1115RecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.policy_bytes = lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes())
        cls.boards = [json.loads(line) for line in lzma.decompress(
            (FIXTURE / "boards.jsonl.xz").read_bytes()).decode("utf-8").splitlines() if line]

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.ledger = Path(scratch.name) / "knowledge.jsonl"
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.policy_bytes)
        self.addCleanup(lambda: self.policy._home_disposal.history_path.unlink(missing_ok=True))

    def deliver(self, entry):
        """Deliver one decision's inputs; its board, raw and parsed."""
        policy = self.policy
        _consume_response_sequence(
            [json.dumps(record, ensure_ascii=False) + "\n" for record in entry["inputs"]],
            policy, lambda _key: True, policy._monrace_knowledge, parse_snapshots=False,
            knowledge_ledger_path=self.ledger)
        raw = copy.deepcopy(entry["inputs"][-1])
        return raw, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)

    def decide(self, raw):
        return str(self.policy.choose_key(parse_snapshot(copy.deepcopy(raw),
                                                         self.policy._monrace_knowledge)))

    def post(self, raw, key, prompts, following):
        """Post ``key`` through the production executor port (ProductionHarness)."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [prompt_screen(text) for text in prompts] + [command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in prompts] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": self.policy.last_reason,
                                            "sequence": self.policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        self.assertTrue(self.policy.confirm_key_posted(key))

    def test_the_recorded_fight_is_on_the_diggers_under_a_refused_rearm(self):
        fight = [entry for entry in self.boards if entry["decision"]["decision_sequence"] < LATCH]
        self.assertEqual({entry["decision"]["reason"] for entry in fight}, {"melee"})
        self.assertTrue(all(entry["decision"]["report"] == "goal-already-superseded"
                            for entry in fight))
        for entry in self.boards:
            raw = entry["inputs"][-1]
            hands = {item["slot"]: item["tval"] for item in raw["equipment"]
                     if item["slot"] in ("main_hand", "sub_hand")}
            self.assertEqual(hands, {"main_hand": 20, "sub_hand": 20})  # TV_DIGGING
            self.assertTrue(letter_of(raw, TRIDENT) and letter_of(raw, RECALL))
            self.assertIn(MOUSE, {monster["race_id"] for monster in raw["visible_monsters"]})
        misses = kills = 0
        for entry in self.boards:
            for line in entry["inputs"][-1].get("messages", ()):
                count = re.search(r"<x(\d+)>", line)
                count = int(count.group(1)) if count else 1
                misses += count * (MISS in line)
                kills += count * (KILL in line)
        self.assertGreater(misses, 10 * kills)
        latched = next(entry for entry in self.boards
                       if entry["decision"]["decision_sequence"] == LATCH)
        self.assertEqual(latched["decision"]["reason"], "breeder-breakthrough:clear-escape-path")

    def test_contact_rearms_the_trident_through_the_executor_and_fights(self):
        raw, _board = self.deliver(self.boards[0])
        key = self.decide(raw)
        self.assertEqual((key, self.policy.last_reason), ("w" + letter_of(raw, TRIDENT) + "a", REARM))
        armed = wielded(raw, TRIDENT, "main_hand")
        self.post(raw, key, (), armed)

        key = self.decide(armed)
        self.assertEqual((key, self.policy.last_reason), ("tb", REARM))
        single = taken_off(armed, "sub_hand")
        self.post(armed, key, (TAKEOFF_PROMPT,), single)

        key = self.decide(single)
        self.assertNotEqual(self.policy.last_reason, REARM)
        self.assertFalse(key.startswith(("w", "t")), (key, self.policy.last_reason))


if __name__ == "__main__":
    unittest.main()
