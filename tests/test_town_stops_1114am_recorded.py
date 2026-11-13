"""The 2026-11-14 morning town stops (bot-dddf29c2f), replayed from their town arrivals.

n1-c life-207 06:29:40, town:blocked:survival:combat_weapon_ready.  The Lv47 Magic-Eater
went down Yeek cave 1F for one supply-stockout mining run (Cure Critical Wounds out of
stock), wielded two diggers ('ta' 'tb', fundraise:wield-digging-tool), found nothing and
climbed back with the same gold, experience and items.  In town the re-arm
(_town_restore_weapon_key -> combat-loadout) was refused by the equipment executor as
"goal-already-superseded": its progress core (gold, experience, item totals) equalled the
one of the mining-loadout posted in the dungeon.  The departure minimum then failed
combat_weapon_ready and the town end stopped by name on the third board of the visit.
The floor is part of the progress core now, so a re-arm after the run is not a flip.

Recorded: the town-arrival checkpoint and its journal
(tests/extract_town_stops_1114am_fixtures.py), decided through the public choose_key;
the re-arm is posted through the production executor (_ExecutorInputPort).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import adopt_calibration, decisions, restore
from tests.support import recorded as executor_harness

FIXTURES = Path(__file__).with_name("fixtures") / "town-stops-1114am"


class Visit:
    """A fixture's arrival policy and journalled boards (calibration only when recorded)."""

    def __init__(self, name):
        source = FIXTURES / name
        self._directory = TemporaryDirectory()
        root = Path(self._directory.name)
        self.scratch = root / "scratch"
        self.scratch.mkdir()
        visit = root / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        self.journal = lzma.decompress((source / "journal.jsonl.xz").read_bytes())
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(self.journal))
        self.policy = restore(visit, self.scratch)
        self.policy._home_disposal.history_path = self.scratch / "home-history.jsonc"
        if (source / "calibration.json").is_file():
            adopt_calibration(self.policy, source / "calibration.json", self.scratch)
        self.rows = list(decisions(self.policy, visit, self.scratch))

    def board(self, row):
        entry = json.loads(self.journal.decode("utf-8").splitlines()[row])
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def close(self):
        self._directory.cleanup()

    def post(self, key):
        policy = self.policy
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class TownStops1114RecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        pass  # The dungeon-1031 corpus of RecordedHarness is not read.

    def visit(self, name):
        visit = Visit(name)
        self.addCleanup(visit.close)
        return visit

    def test_the_town_rearms_the_weapon_after_a_fruitless_mining_run(self):
        visit = self.visit("digger-rearm-207")
        policy = visit.policy
        (recorded, supply), (stop, stop_supply) = visit.rows
        self.assertEqual(recorded["reason"], "town:recover")
        visit.post(policy.choose_key(supply()))
        self.assertEqual(stop["reason"], "town:blocked:survival:combat_weapon_ready")
        board = stop_supply()
        hands = {item.slot: item for item in board.equipment if item.slot in ("main_hand", "sub_hand")}
        self.assertTrue(all(item.is_digging_tool for item in hands.values()), hands)
        spear = next(item for item in board.inventory if item.is_melee_weapon)
        self.assertEqual(spear.name, policy._normal_weapon_name)
        key = policy.choose_key(board)
        self.assertEqual(policy.last_reason, "town:restore-combat-weapon")
        self.assertTrue(key.startswith("w"), key)
        raw = visit.board(1)
        self.assertEqual(self.post(policy, raw, key, [], self.later(raw)), [key])


if __name__ == "__main__":
    import unittest
    unittest.main()
