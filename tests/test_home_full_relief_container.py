"""The full-Home relief's typed container (maintainability review 2026-11-18 (a)-7, owner Q5 「まず
入れ物を整理して様子を見る」).

The relief was a string-keyed dict; ``home_full_relief.HomeFullRelief`` holds the same state in
fixed fields.  These pin the move: an old checkpoint's dict reads into the container with every
value, a field at its default reads as the dict's missing key did, the policy attribute adopts a
written dict, the telemetry observer still works on a copy, and the bot's own code reads fields,
never the dict's string keys.

Recorded: n1-b life-411's town arrival, row 31 (tests/extract_n1b_411_surplus_store_1118_fixture.py),
the one recorded checkpoint whose relief is running.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import lzma
import pickle
import re
import unittest
from pathlib import Path

from hengbot import cli, home_full_relief, state_registry
from hengbot.home_full_relief import HomeFullRelief
from hengbot.latch_onset_capture import load_bytes, restore_checkpoint_bytes
from hengbot.policy import HengbotPolicy

ROW31 = Path(__file__).with_name("fixtures") / "n1b-411-surplus-store-1118" / "row31" / "policy.pkl.xz"
SOURCE = Path(__file__).resolve().parents[1] / "src" / "hengbot"


class OldStateTest(unittest.TestCase):
    def test_the_recorded_dict_reads_into_the_container_unchanged(self):
        payload = lzma.decompress(ROW31.read_bytes())
        saved = load_bytes(payload)["_home_full_relief"]
        self.assertIsInstance(saved, dict)
        policy = restore_checkpoint_bytes(HengbotPolicy, payload)
        relief = policy._home_full_relief
        self.assertIsInstance(relief, HomeFullRelief)
        for key, value in saved.items():
            self.assertEqual(getattr(relief, key), value, key)
        # Every other field is at its default: what the dict's missing key read as.
        for name in home_full_relief.FIELD_NAMES - set(saved):
            self.assertNotIn(name, relief)
        # The container survives its own checkpoint.
        again = pickle.loads(pickle.dumps(relief))
        self.assertEqual(again, relief)

    def test_the_restore_upgrade_reads_the_dict(self):
        state = {"_home_full_relief": {"deposits": (), "remaining": 1, "sale": None,
                                       "withdrawn": False, "town": 1, "sweep": True,
                                       "retired-key": 3}}
        home_full_relief.adopt_saved(state)
        self.assertEqual(state["_home_full_relief"],
                         HomeFullRelief(remaining=1, town=1, sweep=True))


class DictReadingTest(unittest.TestCase):
    def test_a_missing_key_reads_as_the_field_default(self):
        relief = HomeFullRelief(deposits=(), remaining=1, town=1)
        self.assertIsNone(relief.get("mode"))
        self.assertEqual(relief.get("skipped", {}), {})
        self.assertEqual(relief.get("destroy_before_count", 7), 7)
        self.assertNotIn("stock_count", relief)
        # The keys every relief dict was created with are always there.
        self.assertIn("withdrawn", relief)
        self.assertIs(relief.get("withdrawn"), False)
        relief["stock_count"] = 0
        self.assertIn("stock_count", relief)
        self.assertEqual(relief.pop("stock_count", None), 0)
        self.assertNotIn("stock_count", relief)
        relief.setdefault("skipped", {})["a"] = "why"
        self.assertEqual(relief.skipped, {"a": "why"})
        with self.assertRaises(KeyError):
            relief["no-such-field"] = 1

    def test_end_sale_forgets_the_ware(self):
        relief = HomeFullRelief(sale=("s", 1, 0), withdrawn=True, mode="sale", useless="s",
                                round_trip="s", destroy_posted=True, skipped={"t": "x"})
        relief.end_sale(*home_full_relief.SALE_DESTROY_FIELDS)
        self.assertEqual(relief, HomeFullRelief(skipped={"t": "x"}))


class PolicyAttributeTest(unittest.TestCase):
    def test_the_attribute_adopts_a_written_dict(self):
        policy = HengbotPolicy.__new__(HengbotPolicy)
        self.assertIsNone(getattr(policy, "_home_full_relief", None))
        policy._home_full_relief = {"deposits": (), "remaining": 2, "sale": None,
                                    "withdrawn": False, "town": 3}
        self.assertEqual(policy._home_full_relief, HomeFullRelief(remaining=2, town=3))
        self.assertIs(policy.__dict__["_home_full_relief"], policy._home_full_relief)
        policy._home_full_relief = None
        self.assertIsNone(policy._home_full_relief)

    def test_the_observer_works_on_a_copy(self):
        policy = HengbotPolicy.__new__(HengbotPolicy)
        relief = policy._home_full_relief = HomeFullRelief(skipped={"a": "why"})
        before = copy.deepcopy(relief)
        self.assertIn("_home_full_relief", cli._OBSERVER_COPIED_MEMO_OBJECTS)
        duplicate = cli._observer_memo_object_copy(relief)
        duplicate.skipped["b"] = "evaluator"
        duplicate.mode = "sale"
        self.assertEqual(relief, before)


class SourceTest(unittest.TestCase):
    def test_the_bot_reads_fields_not_string_keys(self):
        mapping = re.compile(
            r"""\brelief(\[['"]|\.(get|pop|setdefault|update)\(['"])|['"]\w+['"] (not )?in relief\b"""
            r"""|_home_full_relief = \{""")
        found = [f"{path.name}:{number}: {line.strip()}"
                 for path in sorted(SOURCE.glob("*.py"))
                 # The container's own docstring names the dict's reading it replaces.
                 if path.name != "home_full_relief.py"
                 for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if mapping.search(line)]
        self.assertEqual(found, [])

    def test_the_registry_names_the_container(self):
        self.assertIn("HomeFullRelief", state_registry.BY_NAME["_home_full_relief"].purpose)


if __name__ == "__main__":
    unittest.main()
