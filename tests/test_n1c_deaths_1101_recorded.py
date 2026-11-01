"""D57 (#47): the recorded n1-c Magic-Eater deaths of 2026-11-01 in the Labyrinth.

life-085 (Lv18 zombie, 236 max HP, 迷宮11階, build c326f0fd6):
『スーパー・グレート・シルバー・ゼリー』 (race 1273, EAT_LITE touches, speed
+10) drained the worn unidentified 真鍮のランタン {並, Q34}: 「明かりが暗く
なってしまった。」 four times a turn, then 「明かりが消えてしまった！」 (turn
1445339).  The lamp memory of the refill 108,600 game turns earlier
(「ランプの油は一杯だ。」, turn 1336706) still claimed about 4,100 fuel, so
every refill with the five carried flasks was refused and the dark walk ran
``dark:no-recovery``.  In the dark the jelly stayed in the game's visible list
(infravision; bot-json-output.cpp exports its y/x), but its unlit cell was not
in the grid map and the parser dropped it, so the emergency ladder found no
neighbour and waited (``emergency:wait``) from HP 71 to death beside it.

life-084 (Lv12, 151 max HP, 迷宮14階): a 充血アイ (race 129, NEVER_MOVE,
GAZE:BLIND) blinded it each turn; its Cure Critical Wounds went on the
blindness, then, blind, a ジャイアント・サラマンダー bit it and the emergency
ladder waited four turns (HP 61 -> 0) beside the two attackers it had last
seen.  Owner 2026-10-31 (blind_strike): 「盲目で治す薬がないときは…見えない
敵を攻撃することを試みる方が生存確率は上がる。」

Fixtures: tests/fixtures/death-n1c-084-1101.json.gz, death-n1c-085-1101.json.gz
(tests/extract_n1c_deaths_1101_fixtures.py).  Every decision is the public
``choose_key``; posted keys go through the production executor port
(test_town_combat_survival_recorded.MissilePostedKey).
DECLARED RECONSTRUCTED: the staff sequence record is the capture's
``_me_staff_sequence`` (its extras keyed ``wand:<sval>``) with the power list
read; the life-085 lamp memory is the refill reply of turn 1336706
(life-085 jsonlog/bot-decisions.jsonl.1, shop:travel, 「ランプに油を注いだ。」
「ランプの油は一杯だ。」), which the ring does not reach.
DECLARED CONSTRUCTED: the guard cases strip the light messages from the
boards, or start the blind drive without its sighted board, as each states.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import lamp_fuel
from hengbot import me_staff_sequence as sequence
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.magic_eater import MISSILE_REASON
from hengbot.model import parse_snapshot
from tests import test_input_executor as executor_pins
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_town_combat_survival_recorded import MissilePostedKey


FIXTURES = Path(__file__).with_name("fixtures")


def _load(name):
    with gzip.open(FIXTURES / f"death-n1c-{name}-1101.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


CASE_084, CASE_085 = _load("084"), _load("085")
LAMP_FULL_TURN = 1336706
DARK_TURN, JELLY_WAIT_TURN = 1445339, 1445625
JELLY, BLOODSHOT_EYE = 1273, 129
LIGHT_MESSAGES = frozenset({"明かりが暗くなってしまった。", "明かりが消えてしまった！"})
# The game's prompts of the two-key commands these drives post.
PROMPTS = {"q": "どの薬を飲みますか? ", "+": "方向 (ESCで中断)?"}


def new_policy(case):
    policy = loops.new_policy(case, case["skill"], monraces=case["monraces"])
    record = case["sequence"]
    sequence.state(policy).absorbed = {
        int(key) if key.isdigit() else key: count for key, count in record["absorbed"].items()}
    return policy


def boards(case, first, last, *, light_messages=True):
    rows = [copy.deepcopy(raw) for raw in case["boards"] if first <= raw["turn"] <= last]
    if not light_messages:
        for raw in rows:
            raw["messages"] = [m for m in raw["messages"] if m not in LIGHT_MESSAGES]
    return rows


def recorded(case):
    return {row["turn"]: (row["reason"], row["key"]) for row in case["decisions"]}


class PostedDeathKey(MissilePostedKey):
    """Drive the recorded boards; a quaff or an alter key answers its prompt."""

    def drive(self, policy, rows):
        return loops.MeStaffLoopsRecordedTest.drive(self, policy, rows)

    def post(self, policy, raw, key):
        prompt = PROMPTS.get(key[:1])
        if prompt is None or policy.last_reason == MISSILE_REASON:
            return super().post(policy, raw, key)
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.prompt_screen(prompt),
                        executor_pins.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, [key[0], key[1:]])


def lamp_policy():
    """life-085's policy with the lamp memory of its last refill."""
    policy = new_policy(CASE_085)
    # DECLARED RECONSTRUCTED (module docstring): the refill reply.
    reply = dict(copy.deepcopy(CASE_085["boards"][0]), turn=LAMP_FULL_TURN,
                 messages=["ランプに油を注いだ。", "ランプの油は一杯だ。"])
    lamp_fuel.observe(policy, parse_snapshot(reply, policy._monrace_knowledge))
    return policy


class BlindEmergencyStrikeRecordedTest(PostedDeathKey):
    """life-084: blind without a cure, the emergency ladder waited to death."""

    def test_recorded_rows(self):
        rows = recorded(CASE_084)
        self.assertEqual({rows[turn] for turn in (1287976, 1287988, 1287997, 1288008)},
                         {("emergency:wait", "5")})
        sighted = CASE_084["boards"][0]
        self.assertEqual(sighted["turn"], 1287920)
        self.assertIn(BLOODSHOT_EYE, {m["race_id"] for m in sighted["visible_monsters"]})
        for raw in CASE_084["boards"][2:]:
            self.assertTrue(raw["player"]["status"]["blind"], raw["turn"])
            self.assertFalse([item for item in raw["inventory"]
                              if (item["tval"], item["sval"]) == (75, 36)], raw["turn"])

    def test_blind_emergency_strikes_the_remembered_attacker(self):
        rows = self.drive(new_policy(CASE_084), boards(CASE_084, 1287920, 1288008))
        answers = {raw["turn"]: (key, reason) for raw, key, reason in rows}
        for turn in (1287976, 1287988, 1287997, 1288008):
            self.assertEqual(answers[turn], ("+6", "emergency:blind-strike"), turn)

    def test_control_nothing_remembered_invents_no_cell(self):
        # DECLARED CONSTRUCTED: the drive starts blind, so no attacker was seen.
        blind = boards(CASE_084, 1287976, 1288008)
        rows = self.drive(new_policy(dict(CASE_084, boards=blind)), blind)
        self.assertNotIn("emergency:blind-strike", {reason for _raw, _key, reason in rows})


if __name__ == "__main__":
    unittest.main()
