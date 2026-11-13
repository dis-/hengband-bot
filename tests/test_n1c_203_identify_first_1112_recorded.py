"""n1-c life-203's town:blocked:survival:recall_departure_ready stops (2026-11-12 22:38-22:39).

Recorded: two of the three stops' town-arrival checkpoints, journal rows and sidecar files
(tests/extract_n1c_203_identify_first_1112_fixture.py), replayed through the public chooser
and the live CLI's owner-retirement entrance (--owner-retired-log-only).

The Lv37 zombie Magic-Eater (food: wand and staff charges, cmd-eat.cpp
``exe_eat_charge_of_magic_device``, +5000 per charge) came home with both Wands of Wonder
(its staple) empty, an unknown wand (銀メッキの魔法棒) and a Staff of Light of unknown
charges.  The staff sequence priced the Tower's whole-pack recharge with the unknown wand as
the dearest wand kind (4,050 of 8,655; morivant_tower.recharge_all_price), so the trip
(11,135 with fares and supplies) was above its 7,856 gold, and it opened a mining set to earn
it.  The set holds identification until its kit is ready (``mining_holds_identification``),
and the kit's food was what the unidentified devices would answer: the run was refused
(fundraising-no-food) and the town stopped three times.  Owner 2026-11-12:
「充填できない理由と食事ができない理由は鑑定を後回しにしているロジックの不備である」, and
「…食べられる代替の食料も持っている。停止するのは実装に問題がある。」

Fix: a carried device the held source identifies (the absorbed Identify here) is identified
during the mining set too (it spends none of the set's budget); with the staple drained the
carried charged devices are the food.  The fundraising food waiver is unchanged.

Walls, declared: the ``periodic:character-dump`` row writes the dump the restored policy
reads next; the replay writes the dump the game wrote there (the next process's arrival
copy).  ``test_drained_staple_eats_the_identified_staff`` gives the Staff of Light the
charges its identification would show (DECLARED CONSTRUCTED: the result is not captured).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import copy
import gzip
import json
import lzma
import time
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from hengbot import me_staff_sequence, morivant_tower
from hengbot.cli import _handle_owner_retirement
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from hengbot.town_terminal import gather_identify_device
from replay_town_arrival import adopt_calibration, decisions, journal, restore


FIXTURES = Path(__file__).with_name("fixtures") / "n1c-203-identify-first-1112"
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
STOP = "town:blocked:survival:recall_departure_ready"
TVAL_STAFF, TVAL_WAND, SV_STAFF_LIGHT = 55, 65, 8


class N1c203IdentifyFirst1112RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, stop):
        visit = self.scratch / stop / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        fixture = FIXTURES / stop
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((fixture / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = self.scratch / stop / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        self.dump = lzma.decompress((fixture / "dump-after-dump-row.txt.xz").read_bytes())
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay_live(self, policy, recorded, steps):
        for row, supply in steps:
            board = supply()
            visit_before = copy.copy(policy._store_visit)
            chosen = policy.choose_key(board)
            self.assertEqual((chosen, policy.last_reason),
                             (recorded[row["row"]]["key"], recorded[row["row"]]["reason"]),
                             row["row"])
            key = policy.validate_read_key(board, chosen)
            key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
            if key:
                policy.confirm_key_posted(key)
                if row["reason"] == "periodic:character-dump":
                    time.sleep(0.05)   # wall: the game writes the dump after the macro
                    Path(policy._character_dump_path).write_bytes(self.dump)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def assert_held_by_the_mining_set(self, policy, board):
        self.assertEqual(policy._fundraising_mode, "prepare")
        self.assertFalse(policy._fundraising_supplies_ready(board))
        self.assertIsNone(policy._find_edible(board))
        self.assertTrue(gather_identify_device(policy, board).source_held)

    def test_arrival_identifies_the_unknown_wand_first(self):
        """22:38:48 visit, row 4 (the mining set opened on row 2).

        Live: ``\\x1b`n(.`` equipment-transaction:travel-home; the devices stayed unknown
        and row 71 stopped.
        """
        policy, recorded, steps = self.load("n1c-203-2238")
        self.assertEqual(recorded[71]["reason"], STOP)
        self.replay_live(policy, recorded, steps[:4])
        board = steps[4][1]()
        self.assert_held_by_the_mining_set(policy, board)
        staff = next(item for item in board.inventory if item.tval == TVAL_STAFF)
        self.assertEqual((staff.sval, staff.known), (SV_STAFF_LIGHT, False))
        wand = next(item for item in board.inventory
                    if item.tval == TVAL_WAND and not item.aware)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (f"mAf{wand.slot}", "identify:device"))

    def test_restart_identifies_the_unknown_wand_first(self):
        """22:39:01 (restarted process), row 7.  Live: ``5`` equipment-transaction:retain-reserved,
        then the stop on row 11.  The unknown wand alone priced 4,050 of the recharge."""
        policy, recorded, steps = self.load("n1c-203-2239")
        self.assertEqual(recorded[11]["reason"], STOP)
        self.replay_live(policy, recorded, steps[:7])
        board = steps[7][1]()
        self.assert_held_by_the_mining_set(policy, board)
        wand = next(item for item in board.inventory
                    if item.tval == TVAL_WAND and not item.aware)
        definitions = morivant_tower.device_definitions()
        fallback = me_staff_sequence._FALLBACK_KINDS
        self.assertEqual(morivant_tower.recharge_all_price(wand, definitions, fallback), 4050)
        supplies = me_staff_sequence.supply_cost(policy, board)
        # The expedition's own departure (with the recall scroll it reads), as the run's target
        # 11,285 was priced; the run's mode no longer leaves the scroll out (n1-b life-394).
        self.assertEqual(me_staff_sequence._expedition_cost(board, supplies), 11285)
        self.assertEqual(board.player.gold, 7856)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (f"mAf{wand.slot}", "identify:device"))

    def test_drained_staple_eats_the_identified_staff(self):
        """Row 7's board with the Staff of Light identified (DECLARED CONSTRUCTED: 10 charges).

        The drained staple no longer leaves the charged staff uneaten: it is the carried
        food, and the mining set's food gate passes without its waiver.
        """
        policy, recorded, steps = self.load("n1c-203-2239")
        self.replay_live(policy, recorded, steps[:7])
        board = steps[7][1]()
        board = replace(board, inventory=type(board.inventory)(
            replace(item, known=True, charges=10, pval=10) if item.tval == TVAL_STAFF else item
            for item in board.inventory))
        staff = next(item for item in board.inventory if item.tval == TVAL_STAFF)
        self.assertEqual(board.player.food_state, "normal")
        self.assertEqual(policy._find_edible(board), staff)
        facts = policy._fundraising_facts(board)
        self.assertTrue(facts.carried_edible)
        self.assertFalse(facts.first_run)
        self.assertTrue(policy._fundraising_food_ready(board))


if __name__ == "__main__":
    unittest.main()
