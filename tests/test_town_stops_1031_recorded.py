"""Issue #47, 2026-10-31: recorded town-family stops of the viewing bots.

Every case starts from a fresh production policy with the source-derived town
map (``test_opening_route_r2_recorded``) and feeds the recorded boards of
``fixtures/town-stops-1031.json.gz`` (see ``extract_town_stops_1031_fixture``)
through the public chooser in their recorded order.  Replies to newly posted
keys are declared constructed; keys are posted through the production
executor.
"""
import tests  # noqa: F401

import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

from hengbot.cli import TOWN_BLOCKED_STOP_LIMIT, _advance_town_blocked_iteration
from hengbot import town_pack_headroom
from hengbot.model import _parse_items, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_opening_route_r2_recorded as round2
from tests import test_unid_deposit_recorded as unid
import tests.test_input_executor as executor_harness


FIXTURE = Path(__file__).with_name("fixtures") / "town-stops-1031.json.gz"


class TownStops1031RecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post
    execute = unid.UnidentifiedDepositRecordedTest.execute

    @classmethod
    def setUpClass(cls):
        round2.OpeningRouteR2RecordedTest.setUpClass()
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.cases = json.load(stream)

    def row(self, case, wanted):
        return next(row for index, row in self.cases[case]["rows"] if index == wanted)

    def replay(self, case, last, *, first=None, skip=(), in_store=False, prepare=None):
        """Feed the recorded rows through the public chooser up to ``last``."""
        policy, _ = round2.OpeningRouteR2RecordedTest().case("1")
        policy._in_store_ops_enabled = in_store
        for race, values in self.cases["monraces"].items():
            facts = dict(values)
            for name in ("flags", "abilities"):
                facts[name] = frozenset(facts[name])
            facts["blows"] = tuple(MonsterBlow(**blow) for blow in facts["blows"])
            policy._monrace_knowledge[int(race)] = MonraceKnowledge(**facts)
        primed, decisions = False, {}
        for index, row in self.cases[case]["rows"]:
            if index in skip or (first is not None and index < first):
                continue
            if row.get("type") == "knowledge":
                knowledge = row["knowledge"]
                if knowledge["category"] == "skill_exp":
                    policy.consume_skill_knowledge(row)
                elif knowledge["category"] == "home":
                    policy.consume_home_knowledge(_parse_items(knowledge["items"], protocol=3))
                continue
            if row.get("type") not in ("player_turn", "store"):
                continue
            board = parse_snapshot(row, policy._monrace_knowledge)
            if not primed:
                policy.prime(board)
                primed = True
                if prepare is not None:
                    prepare(policy)
            if in_store:
                policy.observe_store_screen(board.store is not None)
            decisions[index] = (policy.choose_key(board), policy.last_reason)
            if index == last:
                return policy, row, decisions
        raise AssertionError(f"row {last} not in {case}")

    def test_town1_first_absorb_after_home_is_not_an_oscillation(self):
        # n1-b life-276 08:44: the hungry zombie left Home (two Home pages with
        # the same position-free progress state) and every absorb was rewritten
        # into a walk toward the Alchemist until the detectors retired.
        policy, raw, decisions = self.replay("town1", 115)
        self.assertEqual(decisions[112], ("~9\x1b", "home:request-knowledge-scan"))
        self.assertEqual(decisions[114], ("\x1b", "home:leave-for-pending-withdraw"))
        self.assertEqual(parse_snapshot(raw, policy._monrace_knowledge).player.food_state,
                         "hungry")
        self.assertEqual(decisions[115], ("Ef", "survival:mana-absorb"))
        # DECLARED CONSTRUCTED: the engine's reply to the absorb.
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        self.post(policy, raw, "Ef", following)

    def fuse(self, rows):
        """Drive the production town-block fuse over recorded decision rows."""

        class Recorded:
            # The recorded run stopped with no durable town change, so every
            # row carries the same progress state (DECLARED CONSTRUCTED).
            def _town_progress_fingerprint(self, _snapshot):
                return ("recorded-town-state",)

        policy, snapshot = Recorded(), SimpleNamespace(in_town=True)
        streak, durable, peak = 0, None, 0
        for row in rows:
            policy.last_reason = row["reason"]
            policy.decision_claim = {
                "claim_id": row["claim_id"], "distance": row["distance"],
                "goal": {"kind": row["goal_kind"]},
            }
            streak, durable = _advance_town_blocked_iteration(
                policy, snapshot, streak, durable, key=row["key"])
            peak = max(peak, streak)
        return streak, peak

    def test_loops4_5_walk_and_fight_after_one_block_do_not_trip_the_fuse(self):
        # n1-c life-057 08:34 / 08:45: one town:blocked line, then a walk to the
        # down staircase (08:34) or a fight with a fleeing town monster (08:45)
        # reached TOWN_BLOCKED_STOP_LIMIT and stopped the bot as loop-detected.
        for name in ("walk", "fight"):
            with self.subTest(name):
                rows = self.cases["fuse"][name]
                self.assertTrue(rows[0]["reason"].startswith("town:blocked:"))
                self.assertEqual(len(rows), TOWN_BLOCKED_STOP_LIMIT)
                _, peak = self.fuse(rows)
                self.assertLess(peak, TOWN_BLOCKED_STOP_LIMIT // 2)

    def test_repeated_blocks_between_the_recorded_walk_steps_still_trip_the_fuse(self):
        rows = self.cases["fuse"]["walk"]
        repeated = [rows[0]] * TOWN_BLOCKED_STOP_LIMIT
        self.assertEqual(self.fuse(repeated)[0], TOWN_BLOCKED_STOP_LIMIT)
        # A walk that never closes on its goal still counts every step.
        stalled = [rows[0]] + [dict(row, distance=rows[1]["distance"])
                               for row in rows[1:] if row["goal_kind"] == "Reach"]
        stalled += [stalled[-1]] * (TOWN_BLOCKED_STOP_LIMIT - len(stalled))
        self.assertEqual(self.fuse(stalled)[0], TOWN_BLOCKED_STOP_LIMIT)

    def test_town2_home_first_leave_on_a_later_page_ends_the_entry(self):
        # n1-b life-276 08:49: after an inscribe and a sale on the Alchemist
        # page, the continuation selected a departure-blocking buy, _shop sent
        # it Home first (ESC, shop:home-first-before-purchase), and the entry
        # called that mismatch shop-required-operation-uncomposable and stopped.
        home = self.row("town1", 113)
        alchemist = parse_snapshot(self.row("town1", 108), None).store

        def prepare(policy):
            # DECLARED RECONSTRUCTED: the process had read Home (turn 1092865)
            # and the Alchemist's shelf (turn 1092564) earlier in this life; the
            # capture of the stop starts in the dungeon, so both come from the
            # same life's previous capture (fixture case town1).
            policy.consume_home_knowledge(_parse_items(home["knowledge"]["items"], protocol=3))
            policy._town_supplier_stock[4] = alchemist

        policy, raw, decisions = self.replay(
            "town2", 131, skip={128}, in_store=True, prepare=prepare)
        self.assertEqual(decisions[129], ("{h@0\r", "shop:in-store-inscribe"))
        self.assertEqual(decisions[130], ("d0y", "shop:in-store-sell"))
        self.assertEqual(policy.in_store_decision_telemetry()["fallback"]["shop_reason"],
                         "shop:home-first-before-purchase")
        self.assertEqual(decisions[131], ("\x1b", "shop:in-store-done"))
        self.assertNotIn("required-page-continuation", policy._shop_selector_diagnostics)
        # DECLARED CONSTRUCTED: the engine's reply to the leave is the recorded
        # Alchemist entrance board with the post-sale pack and gold.
        outside = copy.deepcopy(self.row("town2", 128))
        outside.update(turn=raw["turn"] + 1, messages=[],
                       inventory=copy.deepcopy(raw["inventory"]))
        outside["player"]["gold"] = raw["player"]["gold"]
        self.post(policy, raw, "\x1b", outside)
        policy.choose_key(parse_snapshot(outside, policy._monrace_knowledge))
        self.assertFalse((policy.last_reason or "").startswith("town:blocked:"),
                         policy.last_reason)

    @staticmethod
    def unsupplied_magic_eater(policy):
        """DECLARED CONSTRUCTED knowledge the town death's capture lacks.

        The capture holds neither the ``~f`` skill list nor a Home list, so
        both requests would own every board.  The skill list carries the
        Magic-Eater's starting TWO_WEAPON/SHIELD experience (0, 0:
        lib/edit/ClassSkillDefinitions.jsonc class 16) at the board's level,
        and Home is taken as empty: the bot carried no healing potion and no
        escape scroll, the condition of the owner decision.
        """
        skill = copy.deepcopy(round2.OpeningRouteR2RecordedTest.stops["1"]["skill"])
        for row in skill["knowledge"]["skills"]:
            row["exp"] = 0
        skill["player"]["level"] = 8
        policy.consume_skill_knowledge(skill)
        policy.consume_home_knowledge(())

    def test_death2_town_monster_it_cannot_beat_is_fought_not_hunted(self):
        # n1-c life-056 08:24 (and lives 050, 053 the same way): HP 37/129, no
        # potion, no escape scroll, near-useless melee.  The town hunt walked to
        # a Scruffy-looking horse it could not beat, fled a step when bitten,
        # walked back, and so on until it died.  Owner 2026-10-31: no refuge,
        # no approach/flee alternation; when attacked with nothing left, fight.
        policy, raw, decisions = self.replay(
            "death2", 66, prepare=self.unsupplied_magic_eater)
        horse = parse_snapshot(raw, policy._monrace_knowledge).visible_monsters[0]
        self.assertEqual((horse.race_id, horse.distance), (955, 3))
        for index in (59, 60, 62, 66):
            with self.subTest(row=index):
                self.assertNotEqual(decisions[index][1], "town:kill-mob-approach")
        for index in (61, 63, 64, 65):
            # The horse is adjacent and biting: attack it, never a flee step.
            with self.subTest(row=index):
                self.assertIn(decisions[index][1],
                              {"flee:cornered-attack", "emergency:cornered-attack"})
        attack = decisions[65][0]
        bitten = self.row("death2", 65)
        # DECLARED CONSTRUCTED: the engine's reply to the attack.
        following = copy.deepcopy(bitten)
        following["turn"] += 10
        following["messages"] = []
        self.post(policy, bitten, attack, following)

    def test_death2_last_known_cell_of_an_unbeatable_monster_is_not_walked_to(self):
        # 223052-223304 after the earlier chase: whenever the horse left sight
        # (HP 15 down to 5) the hunt walked toward the cell where it had last
        # been seen, and bitten again the bot fled a step.
        policy, raw, decisions = self.replay(
            "death2", 118, prepare=self.unsupplied_magic_eater)
        self.assertEqual(parse_snapshot(raw, policy._monrace_knowledge).visible_monsters, [])
        for index in (104, 105, 106, 111, 113, 118):
            with self.subTest(row=index):
                self.assertNotEqual(decisions[index][1], "town:kill-mob-approach")
        for index in (107, 108, 109, 110):
            with self.subTest(row=index):
                self.assertEqual(decisions[index][1], "emergency:cornered-attack")

    def test_key3_distant_store_landmark_is_never_walked_as_a_direction(self):
        # n1-a life-447 08:42: travel to Home was refused by the town pack
        # budget (loot on the town floor, pack 19/23) and no first step was
        # known, so the Home landmark itself was walked as one direction key:
        # '3' from the Alchemist's entrance into its permanent wall at (38,92).
        # The bump cost no game time and the arrival wait stopped the bot.
        policy, raw, decisions = self.replay("key3", 90)
        here = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual((here.player.position.y, here.player.position.x), (37, 91))
        wall = here.grid_at(type(here.player.position)(38, 92))
        self.assertFalse(wall.passable)  # observed: the shop's permanent wall
        for index, (key, reason) in decisions.items():
            with self.subTest(row=index):
                self.assertFalse(key == "3" and reason == "shop:approach", reason)
                self.assertNotEqual(key, "None")
        key, reason = decisions[90]
        self.assertEqual((key, reason), ("qc", "restore:quaff-str"))
        # DECLARED CONSTRUCTED: the quaff prompt and the engine's reply.
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["messages"] = []
        self.execute(policy, raw, key, following,
                     [executor_harness.prompt_screen(
                         "(持ち物:a-z, ESCで中断) どの薬を飲みますか?")], [raw], ["q", "c"])

    def test_town3_refused_staff_purchase_shelves_surplus_at_home_first(self):
        # n1-b life-276 09:00 (and life-274 02:34): the Magic shop sold an
        # affordable Identify staff, but at 19/23 the non-stacking buy left
        # fewer than four free slots; the headroom pass never began, the bot
        # waited for a restock that changes nothing and stopped as
        # departure-unsatisfiable.
        policy, raw, decisions = self.replay("town3", 80, in_store=True)
        magic = parse_snapshot(self.row("town3", 65), policy._monrace_knowledge)
        self.assertEqual((magic.store.store_type, len(magic.inventory)), (5, 19))
        self.assertTrue(any(item.tval == 55 and item.sval == 5
                            for item in magic.store.items))
        for index, (_, reason) in decisions.items():
            with self.subTest(row=index):
                self.assertFalse(reason.startswith("town:wait-restock"), reason)
                self.assertNotEqual(reason, "town:blocked:departure-unsatisfiable")
        self.assertTrue(town_pack_headroom.organizing(
            policy, parse_snapshot(raw, policy._monrace_knowledge)))
        key, reason = decisions[80]
        self.assertEqual(reason, "home:atomic-deposit")
        self.assertTrue(key.startswith("d"), key)

    def test_loop2_failed_torch_restore_is_not_rebuilt_from_another_stack(self):
        # n1-b life-276 06:42-06:46: the restore of the torch taken off the
        # light slot needed a free slot the town pack budget refused at 19/23;
        # each abandon rebuilt the same restore from the other torch stack of
        # the same move identity, and abandon-blocked / town-pack-budget '5'
        # alternated until loop-detected.
        def prepare(policy):
            self.armed_warrior(policy)
            # DECLARED RECONSTRUCTED from the watcher's policy-state.json of
            # 20261031-064611-loop-detected (quoted in LUNA-DIAG-loops.txt):
            # the owned light and the two failure memories, and the blocked
            # restore session being abandoned on this board.
            policy._equipment_transaction_owned_items = [("e1ce6e40a6e45d81", "light")]
            policy._equipment_transaction_failed_items.update(
                {"restore:e1ce6e40a6e45d81", "identity:441248f0e6daf1d7"})
            board = parse_snapshot(self.row("loop2", 85), policy._monrace_knowledge)
            policy._abandon_blocked_equipment_transaction(board)

        policy, raw, decisions = self.replay("loop2", 96, prepare=prepare)
        self.assertIsNone(policy._equipment_transaction_session)
        for index, (key, reason) in decisions.items():
            with self.subTest(row=index):
                self.assertNotIn(reason, {"town-pack-budget",
                                          "equipment-transaction:abandon-blocked"})
        light = next(item for item in parse_snapshot(raw, None).equipment
                     if item.slot == "light")
        self.assertEqual(light.sval, 1)  # the lantern stays worn

    @staticmethod
    def armed_warrior(policy):
        """DECLARED CONSTRUCTED: the capture holds no ~f list and no Home list.

        The Warrior's starting TWO_WEAPON/SHIELD experience (4000, 4000:
        lib/edit/ClassSkillDefinitions.jsonc class 0) at the board's level,
        and an empty Home.
        """
        skill = copy.deepcopy(round2.OpeningRouteR2RecordedTest.stops["1"]["skill"])
        for row in skill["knowledge"]["skills"]:
            if row["id"] in (1, 3):
                row["exp"] = 4000
        skill["player"]["level"] = 18
        policy.consume_skill_knowledge(skill)
        policy.consume_home_knowledge(())
