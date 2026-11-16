"""n1-b life-407's loop stops on Castle 64F (2026-11-16 16:33-16:50): the Magic-Eater wore anti-magic.

Live (Magic-Eater Lv50): in town at 13:31 the equipment transaction swapped 殺戮のセスタス for
☆革グローブ『天豹』 {+器*冷r盲[魔}, whose known flags hold TR_NO_MAGIC (69).  With it worn the
game refuses every ``m`` command before the kind question (io/input-key-processor.cpp
``player_ptr->anti_magic``: 「反魔法バリアが魔法を邪魔した！」, no turn passes;
player-status-flags.cpp has_anti_magic reads the worn items).  The bot still counted its absorbed
*Destruction* and Magic Mapping: each board it chose ``mA3`` (emergency:destruction:absorbed-power)
or ``mAj`` (me-power:new-floor:map-area), the refusal left the board unchanged, and the next
decision of the same turn saw no position change.  On the Broad Axe at (15,23) that made the
floor-item wiggle (policy ``_current_floor_item_key``) step off and seek-loot step back, forever;
in the fights at (14,111) and (15,23) the *Destruction* was asked every turn and the turn went
to a cornered blow among 26-46 monsters.  Three loop-detected stops in 17 minutes.

Two readers had the anti-magic wrong: the success of an absorbed power (me_power_success, the one
owner of the rate) ignored NO_MAGIC, and the loadout search took NO_MAGIC as a monotonic
beneficial flag, so the evaluator scored the gloves without the lost powers.

Recorded: tests/fixtures/n1b-407-anti-magic-1116.jsonl.gz
(tests/extract_n1b_407_anti_magic_1116_fixture.py).  DECLARED CONSTRUCTED: the absorbed staff
list the live process had read and the capture does not carry (*破壊* 6/9 and 周辺感知 3/3, 5%).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_power_success, warrior_loadout_search
from hengbot.magic_eater_devices import power_command_refused
from hengbot.me_device_attacks import observe_lists
from hengbot.me_loadout_offense import MagicEaterOffenseInputs, survival_factor
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy
from tests.test_me_device_attacks import power_list, row


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-407-anti-magic-1116.jsonl.gz"
FIXTURE_SHA256 = "1c60178453ff637473a50e70d95608f652f2257b38f7ec926947995e5aa37235"
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
DESTRUCTION = ("staff", 29)
DESTRUCTION_LEVEL = 50  # BaseitemDefinitions.jsonc, me_loadout_offense.SURVIVAL_POWERS
NO_MAGIC = 69  # object-enchant/tr-types.h TR_NO_MAGIC (反魔法)


def _rows():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


ROWS = _rows()
SKILL = ROWS[0]["board"]


def _boards(window):
    return [row["board"] for row in ROWS if row["role"] == "board" and row["window"] == window]


def _decisions(window):
    return [(row["decision"]["key"], row["decision"]["reason"])
            for row in ROWS if row["role"] == "decision" and row["window"] == window]


def _replay(window):
    """Every board of ``window`` through the public ``choose_key`` of one fresh policy that holds
    the absorbed staffs: [(turn, key, reason)]."""
    boards = _boards(window)
    with TemporaryDirectory() as directory:
        policy = _policy(Path(directory), MONRACE)
        first = parse_snapshot(copy.deepcopy(boards[0]), MONRACE)
        policy.prime(first)
        policy.consume_skill_knowledge({**SKILL, "player": {"level": first.player.level}})
        observe_lists(policy, parse_snapshot(dict(
            copy.deepcopy(boards[0]), turn=boards[0]["turn"] - 1,
            _magic_eater_power_list=power_list(
                "staff", row("*破壊*", 5, current=6, count=9),
                row("周辺感知", 5, current=3, count=3))), MONRACE))
        decided, previous = [], None
        for raw in boards:
            raw = copy.deepcopy(raw)
            if previous is not None:
                raw["_completed_operation_owner"] = previous
            key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, MONRACE)))
            previous = policy.last_reason
            decided.append((raw["turn"], key, previous))
            if key:
                policy.confirm_key_posted(key)
        return decided


class AntiMagicRecordedTest(unittest.TestCase):
    def test_the_fixture_is_the_recorded_loop(self):
        self.assertIn(("mAj", "me-power:new-floor:map-area"), _decisions("loot"))
        self.assertIn(("mA3", "emergency:destruction:absorbed-power"), _decisions("fight"))
        for window in ("loot", "fight"):
            arms = next(item for item in _boards(window)[0]["equipment"] if item["slot"] == "arms")
            self.assertIn(NO_MAGIC, arms["known_flags"])

    def test_the_worn_anti_magic_refuses_every_power(self):
        snapshot = parse_snapshot(copy.deepcopy(_boards("fight")[0]), MONRACE)
        self.assertTrue(me_power_success.worn_anti_magic(snapshot))
        self.assertTrue(power_command_refused(snapshot))
        self.assertEqual(me_power_success.fail_percent(
            object(), snapshot, "staff", DESTRUCTION_LEVEL,
            row=row("*破壊*", 5, current=6, count=9)), me_power_success.REFUSED_FAILURE)
        self.assertEqual(me_power_success.success_percent(
            object(), snapshot, "staff", DESTRUCTION_LEVEL), 0)

    def test_the_loot_alternation_casts_no_power(self):
        decided = _replay("loot")
        self.assertFalse([entry for entry in decided if (entry[1] or "").startswith("m")], decided)

    def test_the_fight_casts_no_destruction(self):
        decided = _replay("fight")
        self.assertFalse([entry for entry in decided if (entry[1] or "").startswith("m")], decided)
        # Without a usable *Destruction* on 64F the existing 50F+ rule reads Word of Recall.
        self.assertEqual(decided[0][1:], ("re", "return:recall"))


class AntiMagicLoadoutTest(unittest.TestCase):
    def test_no_magic_is_not_a_dominating_flag(self):
        self.assertEqual(me_power_success.TR_NO_MAGIC, NO_MAGIC)
        self.assertNotIn(NO_MAGIC, warrior_loadout_search.BENEFICIAL_GEAR_FLAGS)
        self.assertIn(NO_MAGIC, warrior_loadout_search.WARRIOR_EVALUATOR_FLAGS)

    def test_the_recorded_gloves_take_the_survival_powers_away(self):
        arms = next(item for item in _boards("fight")[0]["equipment"] if item["slot"] == "arms")
        flags = frozenset(arms["known_flags"])
        inputs = MagicEaterOffenseInputs(level=50, natural_int=18, survival_powers=(DESTRUCTION,))
        self.assertEqual(survival_factor(inputs, 0, flags, ()), 0.0)
        self.assertGreater(
            survival_factor(inputs, 0, flags - {NO_MAGIC}, ()), 0.9)


if __name__ == "__main__":
    unittest.main()
