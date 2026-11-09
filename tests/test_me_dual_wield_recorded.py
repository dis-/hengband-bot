"""#47: the Magic-Eater dual wields with a to-hit that misses (n1-c, 2026-11-01).

Owner 2026-11-01: 「あたりもしない二刀流を使っていることを改善するべき。」

Root 1 (life-077, build 577cd246b): the Q34 lantern is worn unidentified,
sensed {average} (owner 2026-10-31 「並なら付けて良い」).  The calibration
(character_sheet.derive_equipped_calibration) refused every C screen with any
unidentified worn item ("equipment-stat-modifiers-unknown"), so the optimizer
returned calibration-required for the whole life and never replaced the
Main Gauche / broken dagger dual wield (dump: to-hit -63 / -58) with the
Long Sword (2d5) (+5,+1) carried.  The recorded periodic dump of turn 440550
is replayed through the CLI's response consumer and the public chooser.

Root 2 (life-086, build c326f0fd6): the digger swap began with the off hand
empty and no optimizer winner cached, so the swap recorded nothing for the
off hand, and the town restore (``_restore_mining_combat_hand_key``) wielded
the first carried melee weapon (Rapier {Q34}) there: 'wnb' at turn 287413.
A fresh process on that board (a restart, nothing remembered) took the same
off-hand fallback, a second weapon unevaluated.
Every key is decided by the public chooser and posted through the production
executor.

DECLARED RECONSTRUCTED: the mining-run state of the swap (mode "mine", one
planned run, detection read on this floor, the quiet streak that admitted the
strip), and the staff sequence's power-list read of the process (both as in
test_barehand_mining_recorded / test_me_town_stops_recorded).
DECLARED CONSTRUCTED: the game's reply to a key the recorded process did not
post (the digger taken off into the pack, ten game turns later); the control
board with the lantern unsensed.

Fixture: tests/extract_me_dual_wield_fixture.py.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import copy
import gzip
import hashlib
import json
import string
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_staff_sequence
from hengbot.cli import _ExecutorInputPort, SendResult, _consume_response_sequence, _transport_key
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import ConservativePolicy
from hengbot.policy_constants import (
    CHARACTER_DUMP_MACRO, MINING_THREAT_FREE_LIMIT, SKILL_KNOWLEDGE_MACRO,
)
from tests import test_input_executor as harness
from tests.test_input_executor import FaithfulHookGame, command_screen, prompt_screen

from tests.support.recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
CASE = FIXTURES / "me-dual-wield-20261101.json.gz"
DUMP = FIXTURES / "me-dual-wield-20261101.bot-test2.txt.gz"
SHA256 = {
    CASE: "3ff7b55caa388f2e2ac874273888aadc7c35d804c83505eb92d1cbba2044ba91",
    DUMP: "3266396b27e990fe9417a64a95e23fe470df46c5ca4fb97d5a989f5333bc5c63",
}
HOME_KNOWLEDGE_MACRO = "~9\x1b\x1b"
LONG_SWORD, MAIN_GAUCHE, BROKEN_DAGGER = "ロング・ソード", "マン・ゴーシュ", "折れたダガー"
SHORT_SWORD, RAPIER, PICK = "ショート・ソード", "レイピア", "つるはし"
STRIP, RESTORE = "fundraise:wield-digging-tool", "town:restore-combat-weapon"
# cmd-item/cmd-equipment.cpp do_cmd_wield / do_cmd_takeoff open the item prompt.
ITEM_PROMPTS = {"w": "(Inven: a-w, ESC) どれを装備しますか?",
                "t": "(Equip: a-l, ESC) どれを装備からはずしますか?"}


# Shaped like the recorded body armour row (test_barehand_mining_recorded).
SHIELD = {
    "ac": 2, "aware": True, "charges": 0, "charging": False, "count": 1,
    "damage_dice": {"num": 0, "sides": 0}, "fully_known": False,
    "inscription": "", "is_artifact": False, "is_bounty": False,
    "is_broken": False, "is_cursed": False, "is_ego": False,
    "is_equipment": True, "known": True, "known_flags": [],
    "name": "Small Leather Shield [2,+0]", "pval": 0, "slot": "?",
    "sval": 2, "to_a": 0, "to_d": 0, "to_h": 0, "tval": 34, "weight": 50,
}


def carrying(line, item):
    """The board line with ``item`` carried last in the pack (DECLARED CONSTRUCTED)."""
    board = json.loads(line)
    used = {carried["slot"] for carried in board["inventory"]}
    board["inventory"].append(dict(copy.deepcopy(item), slot=next(
        letter for letter in string.ascii_lowercase if letter not in used)))
    return json.dumps(board, ensure_ascii=False)


def hands(raw):
    return {item["slot"]: item["name"] for item in raw["equipment"]
            if item["slot"] in ("main_hand", "sub_hand")}


def taken_off(raw, slot):
    """The board after ``slot`` was taken off (DECLARED CONSTRUCTED)."""
    after = copy.deepcopy(raw)
    item = next(i for i in after["equipment"] if i["slot"] == slot)
    after["equipment"].remove(item)
    after["inventory"].append(dict(item, slot="?"))
    for letter, carried in zip(string.ascii_lowercase, after["inventory"]):
        carried["slot"] = letter
    after["turn"] += 10
    after["messages"] = []
    return after


class MagicEaterDualWieldRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
        cls.case = json.loads(gzip.decompress(CASE.read_bytes()).decode("utf-8"))
        cls.dump = gzip.decompress(DUMP.read_bytes())
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def consume(self, policy, directory, lines):
        _decoded, snapshots = _consume_response_sequence(
            lines, policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl")
        return snapshots

    # -- root 1: the worn {average} light and the calibration ---------------

    def dumped(self, directory, edit=None):
        """The life-077 process at the recorded dump, through the dump's board."""
        life = dict(self.case["life077"])
        if edit is not None:
            for name in ("before_dump", "after_dump"):
                board = json.loads(life[name])
                edit(board)
                life[name] = json.dumps(board, ensure_ascii=False)
        policy = _policy(directory, self.monrace)
        policy._character_calibration_path.unlink()  # a fresh life: no record
        policy._character_dump_path = directory / "bot_test2.txt"
        self.consume(policy, directory, [life["town"]])
        policy.confirm_key_posted(SKILL_KNOWLEDGE_MACRO)
        self.consume(policy, directory, [life["skill"]])
        policy.confirm_key_posted(HOME_KNOWLEDGE_MACRO)
        self.consume(policy, directory, [life["home"]])
        self.consume(policy, directory, [life["before_dump"]])
        # The recorded decision 1316 posted the periodic dump on this board.
        policy._prepare_character_sheet_dump()
        policy._character_dump_path.write_bytes(self.dump)  # the game writes it
        policy.confirm_key_posted(CHARACTER_DUMP_MACRO)
        (after,) = self.consume(policy, directory, [life["character"], life["after_dump"]])
        # DECLARED RECONSTRUCTED: this process had read the staff power list.
        me_staff_sequence.state(policy).powers_read = True
        policy.choose_key(after)
        return policy, after

    def test_capture_pins_the_recorded_dual_wield(self):
        life = self.case["life077"]
        rows = {row["decision_sequence"]: row for row in life["decisions"]}
        self.assertEqual((rows[1316]["reason"], rows[1316]["key"]),
                         ("periodic:character-dump", CHARACTER_DUMP_MACRO))
        self.assertEqual(rows[1317]["calibration"]["unavailable_reason"],
                         "equipment-stat-modifiers-unknown")
        board = json.loads(life["before_dump"])
        self.assertEqual({slot: name.split(" ")[0] for slot, name in hands(board).items()},
                         {"main_hand": MAIN_GAUCHE, "sub_hand": BROKEN_DAGGER})
        light = next(item for item in board["equipment"] if item["slot"] == "light")
        self.assertEqual((light["known"], light["pseudo_feeling"], light["inscription"]),
                         (False, "average", "Q34"))
        self.assertTrue(any(item["name"].startswith(LONG_SWORD) for item in board["inventory"]))
        sheet = self.dump.decode("euc-jp")
        self.assertIn("(-63,+3)", sheet)
        self.assertIn("(-58,+1)", sheet)

    def test_worn_average_light_keeps_the_calibration_and_the_long_sword_wins(self):
        with TemporaryDirectory() as raw:
            policy, after = self.dumped(Path(raw))
            self.assertIsNotNone(policy._character_calibration,
                                 policy._calibration_unavailable_reason)
            state = policy.equipment_optimization_state(policy.with_known_skill_exp(after))
            self.assertIs(state["calibration"]["present"], True)
            self.assertNotEqual(state["result_source"], "calibration-required-return")
            best = policy._equipment_optimization_preparation.result.best.loadout
            self.assertTrue(best.item_at("main_hand").item.name.startswith(LONG_SWORD))
            self.assertIsNone(best.item_at("sub_hand"))

    def test_control_unsensed_worn_light_still_refuses_the_calibration(self):
        # DECLARED CONSTRUCTED: the dump's boards with the lantern unsensed.
        def unsensed(board):
            light = next(item for item in board["equipment"] if item["slot"] == "light")
            light.pop("pseudo_feeling")
        with TemporaryDirectory() as raw:
            policy, _after = self.dumped(Path(raw), unsensed)
            self.assertIsNone(policy._character_calibration)
            self.assertEqual(policy._calibration_unavailable_reason,
                             "equipment-stat-modifiers-unknown")

    # -- root 2: the digger swap from an empty off hand ----------------------

    def post(self, policy, raw, key, following):
        """Post ``key`` through the production executor; ``following`` is the reply."""
        # observed_input._compile_*: a bare 'w'/'t' + item waits for the item
        # prompt; a hand or dual-wield answer after it ('woa', 'wqy') has no
        # recorded chooser plan and is posted whole, as live.
        observed = key[0] in ITEM_PROMPTS and len(key) == 2
        prompts = [prompt_screen(ITEM_PROMPTS[key[0]])] if observed else []
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = prompts + [command_screen(following["turn"])]
        game.states = [copy.deepcopy(raw) for _ in prompts] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), _transport_key(key, True))
        self.assertTrue(policy.confirm_key_posted(key))

    def decide(self, policy, directory, line):
        (board,) = self.consume(policy, directory, [line])
        return str(policy.choose_key(board))

    def test_swap_from_an_empty_off_hand_restores_it_empty(self):
        life = self.case["life086"]
        recorded = [(row["turn"], row["key"], row["reason"]) for row in life["decisions"]]
        self.assertIn((287413, "wnb", RESTORE), recorded)
        self.assertNotIn("sub_hand", hands(json.loads(life["mine"][0])))
        self.swap_and_restore(life["mine"], life["town"])

    def test_swap_from_an_empty_off_hand_does_not_add_a_carried_shield(self):
        # DECLARED CONSTRUCTED: the recorded boards with a Small Leather Shield
        # carried.  The swap displaced nothing from the off hand, so nothing
        # unevaluated goes into it.
        life = self.case["life086"]
        self.swap_and_restore(*([carrying(line, SHIELD) for line in life[name]]
                                for name in ("mine", "town")))

    def swap_and_restore(self, mine, town):
        life = self.case["life086"]
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = ConservativePolicy(monrace_knowledge=self.monrace)
            (first,) = self.consume(policy, directory, [life["mine"][0]])
            policy.prime(first)
            policy.confirm_key_posted(SKILL_KNOWLEDGE_MACRO)
            self.consume(policy, directory, [life["skill"]])
            # DECLARED RECONSTRUCTED (module docstring).
            policy._fundraising_mode = "mine"
            policy._planned_mining_runs, policy._mining_runs_completed = 1, 0
            policy._mining_scroll_used_floor = first.floor_key
            policy._mining_threat_free_streak = MINING_THREAT_FREE_LIMIT
            me_staff_sequence.state(policy).powers_read = True
            # The recorded swap: the sword off, the two diggers on.
            for index, expected in enumerate(("ta", "wq", "wqy")):
                key = self.decide(policy, directory, mine[index])
                self.assertEqual((key, policy.last_reason), (expected, STRIP))
                self.post(policy, json.loads(mine[index]), key, json.loads(mine[index + 1]))
            # Back in town: the ~f list, then the sword back into the main hand.
            self.consume(policy, directory, [town[0]])
            policy.confirm_key_posted(HOME_KNOWLEDGE_MACRO)
            self.consume(policy, directory, [life["home"]])
            key = self.decide(policy, directory, town[1])
            self.assertEqual(key, SKILL_KNOWLEDGE_MACRO)
            policy.confirm_key_posted(key)
            self.consume(policy, directory, [life["skill"]])
            key = self.decide(policy, directory, town[2])
            self.assertEqual((key, policy.last_reason), ("woa", RESTORE))
            self.post(policy, json.loads(town[2]), key, json.loads(town[3]))
            self.assertEqual(hands(json.loads(town[3]))["main_hand"].split(" ")[0], SHORT_SWORD)
            # The off hand the swap found empty goes back empty (recorded: 'wnb',
            # the Rapier {Q34} into it).
            key = self.decide(policy, directory, town[3])
            self.assertEqual((key, policy.last_reason), ("tb", RESTORE))
            bare = taken_off(json.loads(town[3]), "sub_hand")
            self.post(policy, json.loads(town[3]), key, bare)
            self.assertNotIn("sub_hand", hands(bare))
            key = self.decide(policy, directory, json.dumps(bare, ensure_ascii=False))
            self.assertNotEqual(policy.last_reason, RESTORE)
            self.assertFalse(key.startswith(("w", "t")), (key, policy.last_reason))

    def test_restarted_process_takes_the_digger_off_the_off_hand(self):
        # A fresh process on the recorded 287413 board (the sword back, the
        # pick still in the off hand, the Rapier {Q34} carried) knows nothing
        # of the swap; a second weapon is no fallback for the off hand.
        life = self.case["life086"]
        town = life["town"]
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = ConservativePolicy(monrace_knowledge=self.monrace)
            (first,) = self.consume(policy, directory, [town[0]])
            policy.prime(first)
            policy.confirm_key_posted(HOME_KNOWLEDGE_MACRO)
            self.consume(policy, directory, [life["home"]])
            policy.confirm_key_posted(SKILL_KNOWLEDGE_MACRO)
            self.consume(policy, directory, [life["skill"]])
            me_staff_sequence.state(policy).powers_read = True  # DECLARED RECONSTRUCTED
            board = json.loads(town[3])
            self.assertTrue(any(item["name"].startswith(RAPIER) for item in board["inventory"]))
            key = self.decide(policy, directory, town[3])
            self.assertEqual((key, policy.last_reason), ("tb", RESTORE))
            self.post(policy, board, key, taken_off(board, "sub_hand"))


if __name__ == "__main__":
    unittest.main()
