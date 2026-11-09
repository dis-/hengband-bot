"""n1-c Magic-Eater: a failed Magic Mapping (周辺感知) cast is cast again
(owner 2026-11-02 「一度周辺感知に失敗したらその階では二度と使わないように見える。
指定は5回までのリトライ」; rule owner 2026-10-31 「最大5回まで同じ場所で試す」).

Boards and decision rows are recorded (tests/fixtures/me-mapping-retry-1102.json.gz,
see tests/extract_me_mapping_retry_1102_fixture.py): n1-c life-107, Angband 5F
arrival at (61,76).  Decision 5521 (turn 942940) cast map-area (mAj) and
failed, 5522 cast it again and failed (「呪文をうまく唱えられなかった！ <x2>」), 5523
cast it a third time and the game printed nothing (a successful mapping
prints no message), so 5524 explored.  The boards go through the public
choose_key and the production executor.

DECLARED CONSTRUCTED: the absorbed staff list (5 charges each, as
test_me_stage2_powers); the floor's recorded detect-evil/detect-traps rows
(5519, 5520) are seeded as uses; the game's reply screens to the posted keys
(cmd-magiceat.cpp: the kind and power prompts, then the failure message on the
command screen); the five-failure case repeats the 942948 board with the turn
advanced.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
import unittest

from hengbot import me_powers
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from tests import test_me_mining_death_recorded as mining
from tests import test_me_stage2_powers as stage2
from tests.support.recorded import command_screen

FIXTURE = Path(__file__).parent / "fixtures" / "me-mapping-retry-1102.json.gz"
ARRIVAL_MAP = "me-power:new-floor:map-area"
RECEIPT = ("_completed_operation_owner", "_completed_operation_receipt")


def _harness(name):
    return getattr(mining.MagicEaterMiningDeathRecordedTest, name)


class MagicEaterMappingRetryRecordedTest(mining.harness.ProductionHarness):
    choose = _harness("choose")
    post = _harness("post")
    cast = stage2.MagicEaterStage2PowersTest.cast
    assertPower = stage2.MagicEaterStage2PowersTest.assertPower

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.races = {}
        for key, facts in cls.data["monraces"].items():
            facts = copy.deepcopy(facts)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
            cls.races[int(key)] = MonraceKnowledge(**facts)
        cls.rows = {row["decision_sequence"]: row for row in cls.data["rows"]}

    def board(self, turn, after=None):
        """The recorded board of ``turn``, carrying the receipt of the cast
        whose result it is (the executor's board fields on the next snapshot)."""
        raw = copy.deepcopy(self.data["boards"][str(turn)])
        raw["_magic_eater_power_list"] = stage2.staff_list(stage2.staff_rows())
        for name in RECEIPT if after is not None else ():
            raw[name] = copy.deepcopy(after[name])
        return raw

    def policy(self, raw):
        policy = HengbotPolicy(monrace_knowledge=dict(self.races))
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        memory = me_powers.FloorMemory(parse_snapshot(raw, policy._monrace_knowledge).floor_key,
                                       raw["turn"])
        for sequence in (5519, 5520):  # the recorded detect-evil, detect-traps
            row = self.rows[sequence]
            ident = ("staff", me_powers.decode_letter(row["key"][2]))
            memory.uses.append(me_powers.Use(ident, ident, "new-floor",
                                             Position(**row["position"]), row["turn"]))
        policy._me_power_floor = memory
        return policy

    def failed_cast(self, policy, raw, key):
        failure = command_screen(raw["turn"] + 10)
        failure["lines"][0] = stage2.FAILED
        after = self.cast(policy, raw, key, stage2.staff_rows(), after=[failure])
        self.assertEqual(after["_completed_operation_receipt"]["refusal"], "failed:magic-eater")
        return after

    def test_recorded_failures_are_cast_again_until_the_mapping_succeeds(self):
        rows = self.rows
        here = rows[5521]["position"]
        self.assertEqual([(rows[n]["reason"], rows[n]["key"], rows[n]["position"]) for n in (5521, 5522, 5523)],
                         [(ARRIVAL_MAP, "mAj", here)] * 3)
        self.assertEqual(rows[5522]["messages"], [stage2.FAILED])
        self.assertEqual(rows[5523]["messages"], [stage2.FAILED + " <x2>"])
        self.assertEqual((rows[5524]["reason"], rows[5524]["messages"]), ("explore", []))
        mapping = me_powers.BY_KEY[("staff", stage2.MAPPING)]

        raw = self.board(942940)
        policy = self.policy(raw)
        key = self.choose(policy, raw)
        self.assertPower(policy, key, mapping.letter, ARRIVAL_MAP)
        after = self.failed_cast(policy, raw, key)

        with self.subTest("a step away the arrival mapping is still due"):
            moved = copy.deepcopy(policy)
            board = self.board(942984, after)
            self.assertEqual(board["player"]["x"], here["x"] + 1)
            key = self.choose(moved, board)
            self.assertPower(moved, key, mapping.letter, ARRIVAL_MAP)

        raw = self.board(942948, after)
        key = self.choose(policy, raw)
        self.assertPower(policy, key, mapping.letter, ARRIVAL_MAP)
        after = self.failed_cast(policy, raw, key)
        raw = self.board(942960, after)
        key = self.choose(policy, raw)
        self.assertPower(policy, key, mapping.letter, ARRIVAL_MAP)
        after = self.cast(policy, raw, key, stage2.staff_rows())
        self.assertIsNone(after["_completed_operation_receipt"]["refusal"])
        raw = self.board(942971, after)
        key = self.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, ARRIVAL_MAP, key)
        self.assertEqual([use.used for use in policy._me_power_floor.uses].count(mapping.ident), 1)

    def test_five_failures_at_the_recorded_place_then_the_next_power(self):
        raw = self.board(942948)
        policy = self.policy(raw)
        mapping = me_powers.BY_KEY[("staff", stage2.MAPPING)]
        for failure_number in range(1, me_powers.FAILURES_PER_PLACE + 1):
            key = self.choose(policy, raw)
            self.assertPower(policy, key, mapping.letter, ARRIVAL_MAP)
            after = self.failed_cast(policy, raw, key)
            raw = dict(self.board(942948, after), turn=after["turn"])
        key = self.choose(policy, raw)
        self.assertNotEqual(policy.last_reason, ARRIVAL_MAP, key)
        self.assertEqual(me_powers.FAILURES_PER_PLACE, 5)


if __name__ == "__main__":
    unittest.main()
