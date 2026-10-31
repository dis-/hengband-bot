"""D50 (2026-10-31 22:3x): n1-c life-072 kept a Short Sword over a Home Long Sword.

The recorded Lv14 Magic-Eater wields Short Sword (1d7) (+0,+0) at weapon
proficiency 5711 (calc_to_hit: +8); Home holds Long Sword (2d5) (+1,+4) at
1376, Unskilled (-13).  Against AC 100 the Long Sword hit on the 5% floor, so
the optimizer kept the Short Sword (recorded decision 434: band 19, melee
6.30, the one action a Glaive deposit).  Owner decision 2026-10-31
(「不慣れな武器を見込みで評価」, option B): keep AC 100 but rate a weapon below
Beginner proficiency as if it had Beginner (4000), for every class.

Every decision goes through the public choose_key; keys are posted through
the production executor.  DECLARED RECONSTRUCTED: the capture has no
character dump, so the calibration is built from the board's printed stats
(no worn STR/DEX/CON modifier; its hand to-hit 12 plus skill/3 reproduces
the board's main_hand_to_h 43) and the max-HP inverse.  DECLARED CONSTRUCTED:
the boards after the posted withdraw and the equipment keys (the capture
diverges there).
"""
import tests  # noqa: F401 -- isolate runtime files

import copy
import gzip
import hashlib
import io
import json
import string
import time
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _consume_response_sequence,
    _send_decision_key_with_prompt_chain,
)
from hengbot.equipment_optimizer import Loadout, OwnedEquipment
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.warrior_equipment_evaluator import WarriorCombatInputs, evaluate_warrior_melee
from hengbot.warrior_loadout_evaluator import constitution_hp_bonus
from hengbot.warrior_optimization import CharacterCalibration
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "me-weapon-proficiency-20261031.json.gz"
SHA256 = "b6be89eab5d87359123bd630a2fc663080b15cb0357520bb3f37ff1cec6c9aa3"
LONG_SWORD = (23, 17)
SHORT_SWORD = (23, 10)
WARRIOR = 0
TVAL_LIGHT = 39
ITEM_PROMPTS = {"w": "(Inven: a-p, ESC) どれを装備しますか?",
                "t": "(Equip: a-l, ESC) どれを装備からはずしますか?"}


def reletter(raw):
    for letter, item in zip(string.ascii_lowercase, raw["inventory"]):
        item["slot"] = letter
    return raw


def withdrawn(raw, item):
    """The outside board after the Home withdraw (DECLARED CONSTRUCTED)."""
    after = copy.deepcopy(raw)
    item = {key: value for key, value in item.items() if key != "letter"}
    weapons = [i for i, row in enumerate(after["inventory"])
               if (row["tval"], row.get("sval", 0)) < (item["tval"], item["sval"])]
    after["inventory"].insert(weapons[0] if weapons else len(after["inventory"]), item)
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def takeoff(raw, slot):
    """The board after taking off ``slot`` (DECLARED CONSTRUCTED)."""
    after = copy.deepcopy(raw)
    worn = next(item for item in after["equipment"] if item["slot"] == slot)
    after["equipment"].remove(worn)
    after["inventory"].append(worn)
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def wield(raw, letter):
    """The board after wielding pack ``letter`` (DECLARED CONSTRUCTED)."""
    after = copy.deepcopy(raw)
    item = next(row for row in after["inventory"] if row["slot"] == letter)
    after["inventory"].remove(item)
    slot = "light" if item["tval"] == TVAL_LIGHT else "main_hand"
    worn = next((row for row in after["equipment"] if row["slot"] == slot), None)
    if worn is not None:
        after["equipment"].remove(worn)
        after["inventory"].append(worn)
    after["equipment"].append(dict(item, slot=slot))
    after["turn"] += 10
    after["messages"] = []
    return reletter(after)


def drive_equipment_swap(test, policy, raw, page, done, post):
    """Post the transaction's keys until ``done(board)``; return (board, steps).

    Every reply is DECLARED CONSTRUCTED: the Home withdraw (``page`` is the
    Home page it takes from), the entry back into Home, take-offs and wields.
    ``post(policy, before, key, after, home=None)`` is the executor poster.
    """
    page = copy.deepcopy(page)
    steps = []
    for _step in range(12):
        if done(raw):
            return raw, steps
        key, reason = test.decide(policy, raw)
        steps.append((key, reason))
        home = None
        if key.startswith("5p") and raw.get("store") is None:
            home = dict(copy.deepcopy(raw), store=copy.deepcopy(page))
            stored = next(item for item in page["items"] if item["letter"] == key[2])
            following = withdrawn(raw, stored)
            page["items"].remove(stored)
            for letter, item in zip(string.ascii_lowercase, page["items"]):
                item["letter"] = letter
        elif key == "5" and raw.get("store") is None:
            following = dict(copy.deepcopy(raw), store=copy.deepcopy(page))
        elif key.startswith("t"):
            following = takeoff(raw, policy._equipment_transaction_session.current_action.target_slot)
        elif key.startswith("w"):
            following = wield(raw, key[1])
        else:
            test.fail((key, reason, steps))
        if raw.get("store") is not None and home is None:
            following["store"] = copy.deepcopy(page)
        post(policy, raw, key, following, home=home)
        raw = following
    test.fail(("no end", steps))


def calibration_for(raw):
    """DECLARED RECONSTRUCTED from the printed board (see the module doc)."""
    player = parse_snapshot(raw, {}).player
    stats = tuple(player.stat_use)
    return CharacterCalibration(
        race_id=player.race_id, class_id=player.class_id,
        personality_id=player.personality_id, level=player.level,
        stat_cur=stats, base_stats=stats,
        base_hp=player.max_hp - constitution_hp_bonus(stats[4], player.level),
        base_ac_bonus=0, intrinsic_abilities=frozenset(), schema_version=2,
        source="equipped-c-screen", natural_stats=stats,
        intrinsic_adjustments=(0,) * 6, hp_floor=player.level + 1,
        stat_key_kind="visible-base-current-v2",
        visible_stat_key=player.printed_stat_cur_key,
    )


class MeWeaponProficiencyRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    shop_post = lv7.Lv7TownStopRecordedTest.post

    def post(self, policy, raw, key, following, *, home=None):
        """Post ``key`` through the production executor.

        DECLARED CONSTRUCTED screens: for the withdraw, the Home screens of
        store.cpp for "5" (enter on the entrance), "p" (get), the letter and
        Escape on the recorded Home page ``home`` (as in
        test_idstaff_stockout_kit); for "t"/"w", the item prompt of
        cmd-equipment.cpp (as in test_barehand_mining_recorded).
        """
        def screen(board):
            return (self.shelf_screen(board) if board.get("store")
                    else executor_harness.command_screen(board["turn"]))

        if home is not None:
            prompt = (f"(アイテム:a-{home['store']['items'][-1]['letter']}, ESCで中断) "
                      "どのアイテムを取りますか? ")
            screens = [self.shelf_screen(home), executor_harness.prompt_screen(prompt),
                       self.shelf_screen(home)]
            states = [home] * len(screens)
            expected = ["5", "p", key[2], "\x1b"]
        elif key[0] in ITEM_PROMPTS:
            screens = [executor_harness.prompt_screen(ITEM_PROMPTS[key[0]])]
            states = [raw]
            expected = [key[0], key[1:]]
        else:
            return self.shop_post(policy, raw, key, following)
        game = executor_harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        game.screen = screen(raw)
        game.screens = screens + [screen(following)]
        game.states = [copy.deepcopy(state) for state in states] + [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "me-weapon-proficiency", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract(), in_store=bool(raw.get("store")))
        self.assertTrue(sent, (getattr(port.last_result, "reason", None), game.accepted))
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual(game.accepted, expected)
        policy.confirm_key_posted(key)

    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def board(self, name):
        return copy.deepcopy(self.data["boards"][name])

    def policy(self, raw):
        directory = Path(self.enterContext(TemporaryDirectory()))
        policy = _policy(directory, self.monrace)
        policy._crossarea_fundraising_enforced = True
        policy._character_calibration = calibration_for(raw)
        policy._character_calibration_loaded = True
        policy.prime(parse_snapshot(raw, policy._monrace_knowledge))
        policy.test_directory = directory
        return policy

    def decide(self, policy, raw):
        # The ~f list is the same character's (same level); it is re-read per
        # town visit, as the live process does.
        policy.consume_skill_knowledge(self.data["skill_exp"])
        _decoded, snapshots = _consume_response_sequence(
            [json.dumps(raw, ensure_ascii=False)], policy, lambda _key: True,
            self.monrace, knowledge_ledger_path=policy.test_directory / "knowledge.jsonl")
        return policy.choose_key(snapshots[-1]), policy.last_reason

    def plan(self, policy):
        session = policy._equipment_transaction_session
        return None if session is None else [
            (action.kind, action.item_id.split(":")[0], action.target_slot)
            for action in session.plan.actions]

    def test_fixture_pins_the_recorded_choice(self):
        decision = self.data["decisions"]["434"]
        self.assertEqual((decision["key"], decision["reason"], decision["chosen_band"]),
                         ("\x1b", "home:scan-complete-from-open-page", 19))
        self.assertAlmostEqual(decision["band_descent"][-1]["melee"], 6.3005, places=3)
        self.assertEqual(decision["transaction_next"]["kind"], "deposit")
        home = self.board("home-open")
        worn = next(item for item in home["equipment"] if item["slot"] == "main_hand")
        stored = next(item for item in home["store"]["items"]
                      if (item["tval"], item.get("sval")) == LONG_SWORD)
        self.assertEqual(((worn["tval"], worn["sval"]), worn["weapon_proficiency"]), (SHORT_SWORD, 5711))
        self.assertEqual((stored["to_h"], stored["to_d"], stored["weapon_proficiency"]), (1, 4, 1376))
        self.assertEqual(home["player"]["melee"]["main_hand_to_h"], 43)

    def test_unskilled_long_sword_is_rated_at_beginner_proficiency(self):
        raw = self.board("home-open")
        board = parse_snapshot(raw, {})
        player = board.player
        inputs = WarriorCombatInputs(
            level=player.level, class_id=player.class_id,
            natural_str=player.stat_use[0], natural_dex=player.stat_use[3],
            melee_skill=player.melee_skill)
        worn = {item.slot: OwnedEquipment(f"equipped:{item.slot}", item, "equipped",
                                          equipped_slot=item.slot)
                for item in board.equipment if item.is_equipment}
        short = evaluate_warrior_melee(
            Loadout(tuple(sorted(worn.items())), "weapon_shield"), inputs).hands[0]
        # The recorded C screen: to-hit 43 = hand 12 + skill_thn / 3.
        self.assertEqual(short.to_hit + player.melee_skill // 3, 43)
        stored = next(item for item in board.store.items
                      if (item.tval, item.sval) == LONG_SWORD)
        hands = dict(worn, main_hand=OwnedEquipment("home:long", stored, "home"))
        long = evaluate_warrior_melee(
            Loadout(tuple(sorted(hands.items())), "weapon_shield"), inputs).hands[0]
        # 4 (STR/DEX) + trunc((4000 - 4000) / 200); the game now gives -13.
        self.assertEqual(long.to_hit, 4)
        # Quest readiness keeps the game's current value: 4 - 13.
        now = evaluate_warrior_melee(
            Loadout(tuple(sorted(hands.items())), "weapon_shield"), inputs,
            current_proficiency=True).hands[0]
        self.assertEqual(now.to_hit, -9)
        self.assertGreater(long.expected_damage_per_round, short.expected_damage_per_round)

    def test_warrior_control_rates_only_sub_beginner_weapons_up(self):
        """The same board as a Warrior (class 0, DECLARED CONSTRUCTED): all classes."""
        board = parse_snapshot(self.board("home-open"), {})
        player = board.player
        inputs = WarriorCombatInputs(
            level=player.level, class_id=WARRIOR,
            natural_str=player.stat_use[0], natural_dex=player.stat_use[3],
            melee_skill=player.melee_skill)
        stored = next(item for item in board.store.items
                      if (item.tval, item.sval) == LONG_SWORD)

        def to_hit(proficiency):
            weapon = OwnedEquipment("home:long", replace(stored, weapon_proficiency=proficiency), "home")
            return evaluate_warrior_melee(
                Loadout((("main_hand", weapon),), "one_handed"), inputs).hands[0].to_hit

        self.assertEqual(to_hit(1376), to_hit(4000))
        self.assertEqual(to_hit(0), to_hit(4000))
        # Beginner and above keep the game's (exp - 4000) / 200.
        self.assertEqual(to_hit(5711), to_hit(4000) + 8)

    def test_long_sword_is_fetched_from_home_and_wielded(self):
        policy = self.policy(self.board("home-open"))
        key, reason = self.decide(policy, self.board("home-open"))
        self.assertEqual((key, reason), ("\x1b", "home:scan-complete-from-open-page"))
        plan = self.plan(policy)
        # Unfixed: [('deposit', 'pack', None)] (the Glaive only).
        self.assertIn(("withdraw", "home", None), plan)
        self.assertIn(("equip", "home", "main_hand"), plan)
        self.post(policy, self.board("home-open"), key, self.board("outside-1"))
        for name in ("outside-1", "outside-2"):
            self.decide(policy, self.board(name))
        key, reason = self.decide(policy, self.board("home-reentered"))
        self.assertEqual((key, reason), ("dn", "equipment-transaction:deposit"))
        self.post(policy, self.board("home-reentered"), key, self.board("home-deposited"))
        key, _reason = self.decide(policy, self.board("home-deposited"))
        self.post(policy, self.board("home-deposited"), key, self.board("outside-after-deposit"))
        page = self.board("home-deposited")["store"]
        stored = next(item for item in page["items"]
                      if (item["tval"], item.get("sval")) == LONG_SWORD)
        long_sword_letter = []

        def wielding_long_sword(board):
            letter = next((item["slot"] for item in board["inventory"]
                           if (item["tval"], item.get("sval")) == LONG_SWORD), None)
            if letter is not None:
                long_sword_letter.append(letter)
            main = next((item for item in board["equipment"] if item["slot"] == "main_hand"), {})
            return (main.get("tval"), main.get("sval")) == LONG_SWORD

        raw, steps = drive_equipment_swap(
            self, policy, self.board("outside-after-deposit"), page, wielding_long_sword, self.post)
        self.assertEqual(steps, [
            (f"5p{stored['letter']}\x1b", "equipment-transaction:atomic-withdraw"),
            ("5", "equipment-transaction:travel-home:await-entry"),
            ("tb", "equipment-transaction:takeoff"),  # the Large Leather Shield
            ("ta", "equipment-transaction:takeoff"),  # the Short Sword
            ("w" + long_sword_letter[-1], "equipment-transaction:equip"),
        ])
        main = next(item for item in raw["equipment"] if item["slot"] == "main_hand")
        self.assertEqual((main["tval"], main["sval"], main["to_d"]), (*LONG_SWORD, 4))


if __name__ == "__main__":
    import unittest
    unittest.main()
