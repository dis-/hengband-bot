"""D53: the recorded n1-c stuck-prompt:me-powerful:identify stops of 2026-11-01 (#47).

Lives 072-076 of the viewing Magic-Eater each retired after three
stuck-prompt:me-powerful:* stops.  On a safe town board the Powerful
Activation work (me_powerful_activation.town_key) chose *Identify* and posted
``U``.  The game (cmd-action/cmd-racial.cpp racial_power_process_input) asks
the racial power with input_spell_choice, published as input_context kind
``spell``; the executor owned that prompt only as ``command_char``, refused
it ("unowned racial power prompt") and left it open.

Boards are frozen in tests/fixtures/me-powerful-stuck-20261101.json.gz
(tests/extract_me_powerful_stuck_fixture.py): life-076 (pack target ``q``)
and life-075 (worn target ``/a``).  Every decision is the public
``choose_key``; the recorded key goes through the production executor port
and is answered first on the recorded racial prompt screen.

DECLARED CONSTRUCTED: the fresh process holds the capture's staff sequence
record, its last skill-proficiency and Home knowledge rows (the capture keeps
no process memory); the screens after ``b`` are constructed from the game's
prompts (cmd-magiceat.cpp kind and power prompts, spells-perception.cpp
identify_fully's item prompt and screen_object pages), the staff list with
the recorded *Identify* charges unknown (5 of 21 chosen), and the reply board
with the target fully known.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run
from recorded_junk_scope import install_past_destroyed_junk

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_powerful_activation as powerful
from hengbot import me_staff_sequence as sequence
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import EQUIPMENT_SLOT_KEY
from hengbot.quest_strategies import load_quest_strategies
from tests import test_me_powerful_activation as constructed
from tests.test_input_executor import source_derived_identify_viewer
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "me-powerful-stuck-20261101.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASES = {case["id"].split("/")[0]: case for case in json.load(_stream)}
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"


def recorded_policy(case):
    policy = ConservativePolicy(quest_strategies=load_quest_strategies(STRATEGIES))
    for race, facts in case["monraces"].items():
        facts = copy.deepcopy(facts)
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
        policy._monrace_knowledge[int(race)] = MonraceKnowledge(**facts)
    board = case["board"]
    policy.prime(parse_snapshot(copy.deepcopy(board), policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(copy.deepcopy(case["skill"]), turn=board["turn"]))
    policy.consume_home_knowledge(tuple(_parse_items(
        case["home"]["knowledge"]["items"], protocol=board["protocol_version"])))
    record = sequence.state(policy)
    record.powers_read = case["sequence"]["powers_read"]
    # Staff svals are ints; an extra keeps its device key ("wand:6").
    record.absorbed = {int(key) if key.isdigit() else key: count
                       for key, count in case["sequence"]["absorbed"].items()}
    return policy


def recorded_racial_screen(case):
    """The game's reply to the posted ``U`` (control-at-stop.json)."""
    return copy.deepcopy(case["screen"])


_undo_past_junk = None


def setUpModule():
    # Owner 2026-11-02: these boards carry junk the first safe decision destroys.
    global _undo_past_junk
    _undo_past_junk = install_past_destroyed_junk()


def tearDownModule():
    _undo_past_junk()


class MePowerfulStuckRecordedTest(executor_harness.ProductionHarness):
    post = constructed.MagicEaterPowerfulActivationTest.post

    def choose(self, life):
        case = CASES[life]
        policy = recorded_policy(case)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(case["board"]),
                                               policy._monrace_knowledge))
        return case, policy, key

    @staticmethod
    def identified(raw, target):
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        area = "equipment" if target.startswith("/") else "inventory"
        slot = (next(slot for slot, letter in EQUIPMENT_SLOT_KEY.items() if letter == target[-1])
                if area == "equipment" else target)
        next(item for item in following[area] if item["slot"] == slot)["fully_known"] = True
        return following

    def item_prompts(self, raw, target):
        last = raw["inventory"][-1]["slot"]
        inventory = constructed.prompt(
            constructed.FULL_IDENTIFY_PROMPT, "item", area="inventory",
            areas=["inventory", "equipment"], menu=False, first_label="a", last_label=last)
        if not target.startswith("/"):
            return [inventory]
        equipment = constructed.prompt(
            constructed.FULL_IDENTIFY_PROMPT, "item", area="equipment",
            areas=["inventory", "equipment"], menu=False, first_label="a", last_label="h")
        return [inventory, equipment]

    def test_recorded_stop_is_the_reply_to_the_recorded_racial_command(self):
        for life, case in CASES.items():
            with self.subTest(life=life):
                context = case["screen"]["input_context"]
                self.assertEqual(case["posted"], powerful.RACIAL_KEY)
                self.assertEqual((context["kind"], context["first_label"], context["last_label"],
                                  context["list"]), ("spell", "a", "c", True))

    def test_recorded_boards_compose_the_recorded_identify(self):
        for life in CASES:
            with self.subTest(life=life):
                case, policy, key = self.choose(life)
                decision = case["decision"]
                self.assertEqual((key, policy.last_reason), (decision["key"], decision["reason"]))

    def test_recorded_racial_prompt_is_answered_through_the_chain(self):
        for life in CASES:
            with self.subTest(life=life):
                case, policy, key = self.choose(life)
                raw, target = case["board"], key[len(powerful.IDENTIFY.key):]
                game, board = self.post(policy, raw, key, [
                    recorded_racial_screen(case),
                    constructed.prompt(constructed.TYPE_PROMPT),
                    constructed.staff_powers(),
                    *self.item_prompts(raw, target),
                    source_derived_identify_viewer(),
                    source_derived_identify_viewer(final=True),
                ], self.identified(raw, target))
                # Recorded: U, then stuck-prompt "unowned racial power prompt".
                self.assertEqual(game.accepted,
                                 ["U", "b", "A", "f", *target, " ", "\x1b"])
                key = policy.choose_key(parse_snapshot(board, policy._monrace_knowledge))
                self.assertNotEqual(key, case["decision"]["key"], policy.last_reason)


if __name__ == "__main__":
    unittest.main()
