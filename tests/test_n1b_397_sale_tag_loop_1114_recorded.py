"""The sale's tag keeps the random-teleport '.' (n1-b life-397 2026-11-14 19:24).

n1-b life-397 (Magic-Eater Lv47, build f8c14ff0d2) carried an unselected
(トランプ) トライデント (TR_TELEPORT, uncursed) on its Outpost visit.  The
equipment transaction inscribes every carried uncursed TR_TELEPORT item with
'.' so the optimizer may weigh it (equipment-txn, suppress-random-teleport);
this one was not selected and went to the Weaponsmith to be sold.  The sale
addresses its target by an ``@<digit>`` tag written through the game's
inscription prompt, whose first key replaces the old text, so ``{i@0`` erased
the '.'.  The suppression producer saw the trident pending again, left the
store to write the '.' back ('{i.'), the sale re-entered and tagged it again,
until the loop-detected stop (stop capture 20261114-192446-loop-detected).

Fix: the sale's tag keeps a '.' that is already there (``@0.``).

Recorded: the incident capture 20261114-192441-livelock-exhausted's
town-arrival checkpoint and its first 51 journal rows,
tests/extract_n1b_397_sale_tag_loop_1114_fixture.py, through the public
choose_key with the recorded keys acknowledged.  Row 0 is FORCED (the periodic
character dump's timer runs on the replay's clock).

DECLARED CONSTRUCTED: the board after row 49 is row 50's recorded board with
the trident's inscription the new tag wrote (``@0.``) in place of the recorded
``@0``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-397-sale-tag-loop-1114"
FORCED = {0}
TAG_ROW = 49
TRIDENT_TVAL = 22


class N1b397SaleTagLoop1114RecordedTest(unittest.TestCase):
    def load(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        policy, journal, rows = load(FIXTURE, self.scratch)
        self.addCleanup(lambda: policy._home_disposal.history_path.unlink(missing_ok=True))
        return policy, journal, rows

    def to_trident_tag(self):
        """Rows 0-48 decided as recorded; row 49's decision and the journal."""
        policy, journal, rows = self.load()
        for recorded, supply in rows[:TAG_ROW]:
            key = policy.choose_key(supply())
            if recorded["row"] not in FORCED:
                self.assertEqual((key, policy.last_reason),
                                 (recorded["key"], recorded["reason"]), recorded["row"])
            policy.confirm_key_posted(recorded["key"])
        recorded, supply = rows[TAG_ROW]
        board = supply()
        trident = next(item for item in board.inventory if item.tval == TRIDENT_TVAL)
        self.assertEqual((trident.slot, trident.inscription), ("i", "."))
        # The recorded tag replaced the '.'.
        self.assertEqual((recorded["key"], recorded["reason"]),
                         ("{i@0\r", "shop:in-store-inscribe"))
        key = policy.choose_key(board)
        return policy, journal, key

    def test_the_tag_keeps_the_suppression(self):
        policy, _journal, key = self.to_trident_tag()
        self.assertEqual((key, policy.last_reason), ("{i@0.\r", "shop:in-store-inscribe"))

    def test_the_tagged_trident_is_sold_without_leaving(self):
        policy, journal, key = self.to_trident_tag()
        policy.confirm_key_posted(key)
        entry = journal[TAG_ROW + 1]
        # The recorded loop: the next board left the store to write the '.' back.
        self.assertEqual((entry["key"], entry["reason"]), ("\x1b", "shop:in-store-done"))
        _consume_response_sequence(
            [line + "\n" for line in entry["inputs"]], policy, lambda _key: True,
            policy._monrace_knowledge, parse_snapshots=False,
            knowledge_ledger_path=self.scratch / "knowledge.jsonl")
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        raw = json.loads(entry["line"])
        trident = next(item for item in raw["inventory"] if item["tval"] == TRIDENT_TVAL)
        self.assertEqual(trident["inscription"], "@0")
        trident["inscription"] = "@0."
        self.assertIn("@0}", trident["name"])
        trident["name"] = trident["name"].replace("@0}", "@0.}")
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("d0y", "shop:in-store-sell"))


if __name__ == "__main__":
    unittest.main()
