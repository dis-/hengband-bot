"""Owner 2026-11-02: Angband's random quests wait until after Q2 (rq-after-q2-1102).

「angband 6F, 12Fのランダムクエストに挑む順が早いので達成率が低い。Q2の後に
回したい」.  The viewing Magic-Eater n1-c life-080 (build of 2026-11-01) stood
on the down staircase of 鉄獄5階 at turn 577526 with Q2 (下水道) not taken; its
recorded decision 1872 was ``descend`` '>' and turn 577527 was 鉄獄6階,
random quest 49 (lib/edit/quests/049_RandomQuest.jsonc, level 6).

Pinned through the public chooser and the production executor port on the
recorded boards of the walk onto the staircase: with Q2 open the bot does not
post '>' into the random quest floor; with Q2 resolved the same boards descend
as recorded.

Fixture: tests/fixtures/rq-after-q2-n1c-080-1102.json.gz
(tests/extract_rq_after_q2_fixture.py).
DECLARED RECONSTRUCTED: the absorbed-power memory of this floor visit is the
recorded ``me-power:*`` decisions 1748-1850 (the capture's own record is the
later town's); the quest knowledge is the fixture's RANDOM rows of
lib/edit/quests (production loads every quest file).
DECLARED CONSTRUCTED: the after-Q2 case adds the Q2 row
(QuestStatusType::FINISHED, as make_disclosed_quests_json reports it) to every
board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import gzip
import json
from pathlib import Path

from hengbot import me_powers
from hengbot.cli import SendResult, _ExecutorInputPort, _transport_key
from hengbot.model import Position
from hengbot.policy_constants import DOWN_STAIRS_KEY, QUEST_STATUS_FINISHED
from hengbot.quest_knowledge import QuestInfo
from hengbot.random_quest_hold import GATING_QUEST_ID
from tests import test_me_staff_loops_1031_recorded as loops
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_input_executor import FaithfulHookGame, command_screen


FIXTURE = Path(__file__).with_name("fixtures") / "rq-after-q2-n1c-080-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
DESCENT_TURN = 577526
ANGBAND_5F = (1, 5, 0)
# QuestStatusType::FINISHED row of make_disclosed_quests_json (bot-json-output.cpp).
Q2_FINISHED = {"id": GATING_QUEST_ID, "status": QUEST_STATUS_FINISHED, "type": 6,
               "level": 15, "fixed": True, "name": "下水道", "complev": 20, "comptime": 1}


def power_memory():
    """The floor visit's absorbed-power uses, from the recorded decisions."""
    uses = []
    for row in CASE["power_uses"]:
        ident = (me_powers.kind_of(row["key"][1]), me_powers.decode_letter(row["key"][2]))
        uses.append(me_powers.Use(
            ident, ident, row["reason"].split(":")[1],
            Position(row["position"]["y"], row["position"]["x"]),
            row["turn"], row["reason"], row["key"]))
    return me_powers.FloorMemory(ANGBAND_5F, CASE["power_uses"][0]["turn"], uses)


_undo_past_junk = None


def setUpModule():
    # Owner 2026-11-02: these boards carry junk the first safe decision destroys.
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


class RandomQuestAfterQ2RecordedTest(d57.PostedDeathKey):
    def boards(self, *, q2_done):
        boards = [copy.deepcopy(raw) for raw in CASE["boards"] if raw["turn"] <= DESCENT_TURN]
        if q2_done:
            for raw in boards:
                raw["progress"]["quests"].append(dict(Q2_FINISHED))
        return boards

    def new_policy(self, boards):
        policy = d57.new_policy(dict(CASE, boards=boards))
        policy._quest_knowledge = {row["id"]: QuestInfo(**row) for row in CASE["random_quests"]}
        setattr(policy, me_powers.MEMORY, power_memory())
        return policy

    def send(self, policy, raw, key, following):
        """Post ``key`` through the executor port; the next recorded board answers it."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        return port.last_result.board

    def drive(self, *, q2_done):
        boards = self.boards(q2_done=q2_done)
        policy = self.new_policy(boards)
        rows, raw = [], boards[0]
        for following in [*boards[1:], None]:
            key = loops.decide(policy, raw)
            rows.append((raw["turn"], key, policy.last_reason))
            if following is None:
                break
            following = self.send(policy, raw, key, following)
            policy.confirm_key_posted(key)
            raw = following
        return rows

    def test_recorded_descent_into_random_quest_49(self):
        self.assertEqual(d57.recorded(CASE)[DESCENT_TURN], ("descend", DOWN_STAIRS_KEY))
        quests = {row["id"]: row for row in CASE["random_quests"]}
        self.assertEqual((quests[49]["level"], quests[49]["dungeon"]), (6, 1))
        self.assertNotIn(GATING_QUEST_ID, {row["id"] for row in CASE["boards"][0]["progress"]["quests"]})

    def test_before_q2_the_dive_stops_above_the_random_quest_floor(self):
        rows = self.drive(q2_done=False)
        self.assertEqual(rows[-1][0], DESCENT_TURN)
        self.assertNotIn(DOWN_STAIRS_KEY, [key for _turn, key, _reason in rows], rows)

    def test_after_q2_the_same_boards_descend(self):
        rows = self.drive(q2_done=True)
        self.assertEqual(rows[-1], (DESCENT_TURN, DOWN_STAIRS_KEY, "descend"), rows)


if __name__ == "__main__":
    import unittest

    unittest.main()
