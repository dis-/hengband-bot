"""n1-b (Magic-Eater) life-354 2026-11-09: Q2 never taken for 99 bolts.

Owner 2026-11-09: 「プレイ時間に対して受けない時間が長過ぎる。なんらかの不具合が
強く疑われる」.  Q2 (strategy/quests/QUEST_2.jsonc, ``launcher_ammo: 99``) was
refused at every town decision of the life on that carry alone (41..95
carried) while Home held 54 plain bolts (1d5) (+0,+0) beside the carried
plain stack.

Owner rules restored: 2026-09-14 「購入よりも自宅からの回収の方が優先される」,
2026-10-01 「通常の潜行の買い足しは重量に収まる個数まで（クエスト入場の99は維持）」
and 2026-09-03 「重量超過した場合…過剰分を自宅に預け入れる」.  The pack carried
two breach diggers; Q2's ``wall_breach: 1`` reserves one (the carry-strategy
retention), so the second, ドワーフのつるはし (200), was surplus.  Two defects
kept it over the rounds:

1. ``_ammo_procurement_target`` (Home take, purchase) measured the fit on the
   pack as it stood, the surplus digger included, while the retention side
   (the weight relief) sheds the ordinary surplus before any ammunition: the
   Home take was cut to what fitted beside the digger (18 at row 27).  The
   credit applies under the limit only: an overweight pack sheds first.
2. ``_weight_deposit_candidates`` protected the digger as an unreserved
   "required supply" of the quest carry although the carry's own retention
   had reserved it 0, so the relief deposited bolts instead of the digger
   (rows 36 and 46: 'dl2', 'dk1'; the visit left with 70 bolts at 1700/1700).

Recorded: the arrival checkpoint and journal
(tests/extract_n1b_q2_home_ammo_1109_fixture.py), decided through the public
``choose_key``; the Home after rows 11 and 27 is a constructed engine
(MergingHomeGame, declared below) driven through the production executor.

DECLARED for the row-11 replay: rows 3, 5, 6, 7 (town:seek-shelter picks
another equally near cell on the restored policy, on the recorded build too)
and row 10 (the same travel key under the plain shop:travel reason once
those steps differ) are fed with the recorded key posted.  Row 9 too: the
recorded build read an Identify scroll on the unknown device ('rhk'); the
town device identification now casts the absorbed Identify first (owner
2026-10-30 「以降、鑑定と財宝感知は取り込みで賄う」; 'mAfk', asserted).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import os
import time
import unittest
from tests.support import item_use_route_wall
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _ExecutorInputPort, _consume_response_sequence, _send_new_decision_key
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST
from replay_town_arrival import adopt_calibration, restore
from tests.support import recorded as executor_pins
from tests.test_town_withdraw_pack_budget_recorded import HomeEntranceGame

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-q2-home-ammo-1109"
FORCED = {3, 5, 6, 7, 9, 10}
ABSORBED_IDENTIFY_ROW = (9, "mAfk", "identify:device")
BOLT = 18
PLAIN = "クロスボウの矢 (1d5) (+0,+0) (70/shot 58/turn)"
POWER = "クロスボウの矢 (1d5) (+5,+4) (83/shot 69/turn)"
DWARVEN_PICK = "ドワーフのつるはし"
ORCRIST = "★ブロード・ソード『オルクリスト』"
SPEED = "スピードの薬"
STACK_FIELDS = ("tval", "sval", "name", "to_h", "to_d", "to_a", "known", "inscription",
                "is_ego", "is_artifact", "damage_dice")


class MergingHomeGame(HomeEntranceGame):
    """DECLARED CONSTRUCTED: a taken stack merges into its identical pack stack.

    object-similar ammunition joins the pack stack (inventory_carry); the
    constructed Home otherwise appends it as a separate entry.
    """

    def _transfer(self, kind, item, count):
        if kind == "withdraw":
            same = next((owned for owned in self.pack
                         if all(owned.get(f) == item.get(f) for f in STACK_FIELDS)), None)
            if same is not None:
                if count == item.get("count", 1):
                    self.pages[self.page].remove(item)
                else:
                    item["count"] -= count
                same["count"] += count
                self.message = ""
                return
        super()._transfer(kind, item, count)


class N1bQ2HomeAmmo1109RecordedTest(executor_pins.ProductionHarness):

    def setUp(self):
        item_use_route_wall.hold(self)  # wall, declared: tests/support/item_use_route_wall.py
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        (self.scratch / "runtime-env").mkdir()
        (self.scratch / "history-env").mkdir()
        env = mock.patch.dict(os.environ, {
            RUNTIME_DIR_ENV: str(self.scratch / "runtime-env"),
            HOME_HISTORY_DIR_ENV: str(self.scratch / "history-env")})
        env.start()
        self.addCleanup(env.stop)

    def restore(self):
        self.journal = [json.loads(line) for line in
                        lzma.decompress((FIXTURES / "journal.jsonl.xz").read_bytes()).splitlines()]
        visit = self.scratch / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        sidecars = json.loads(lzma.decompress((FIXTURES / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        (visit / SIDECAR_DIRECTORY).mkdir()
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        # The arrival's character calibration, as replay_town_arrival reads it.
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path", runtime)
        return policy

    def consume(self, policy, row):
        _consume_response_sequence([line + "\n" for line in self.journal[row]["inputs"]], policy,
                                   lambda _key: True, policy._monrace_knowledge,
                                   parse_snapshots=False,
                                   knowledge_ledger_path=self.scratch / "knowledge.jsonl")

    def raw(self, row):
        entry = self.journal[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def decide(self, policy, row):
        self.consume(policy, row)
        entry = self.journal[row]
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        board = parse_snapshot(self.raw(row), policy._monrace_knowledge)
        return board, policy.choose_key(board)

    @staticmethod
    def post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def arrive_at_home(self):
        """Replay rows 0-10; decide the recorded Home page of row 11."""
        policy = self.restore()
        for row in range(11):
            _board, key = self.decide(policy, row)
            recorded = self.journal[row]
            if row not in FORCED:
                self.assertEqual((key, policy.last_reason),
                                 (recorded["key"], recorded["reason"]), row)
            if row == ABSORBED_IDENTIFY_ROW[0]:
                self.assertEqual((row, key, policy.last_reason), ABSORBED_IDENTIFY_ROW)
            self.post(policy, recorded["key"])
        board, key = self.decide(policy, 11)
        return policy, board, key

    def home_shelf(self):
        """The Home of row 11: its recorded page 1 and, for page 2, the
        recorded ~9 catalogue of row 25 without the two stacks deposited
        between the two (recorded rows 15 and 16: Orcrist, one Potion of
        Speed); the page-1 names are checked against the recorded page."""
        knowledge = next(json.loads(line) for line in self.journal[25]["inputs"]
                         if '"knowledge"' in line)["knowledge"]["items"]
        later = [next(i for i, item in enumerate(knowledge) if item["name"].startswith(ORCRIST)),
                 next(i for i, item in enumerate(knowledge) if item["name"] == SPEED)]
        shelf = [{k: v for k, v in item.items() if k != "slot"}
                 for i, item in enumerate(knowledge) if i not in later]
        page = [{k: v for k, v in item.items() if k != "letter"}
                for item in self.raw(11)["store"]["items"]]
        self.assertEqual([item["name"] for item in shelf[:52]], [item["name"] for item in page])
        self.assertEqual(len(shelf), self.raw(11)["store"]["stock_num"])
        return page + shelf[52:]

    def test_overweight_arrival_shelves_the_surplus_digger_not_the_bolts(self):
        policy, board, key = self.arrive_at_home()
        plain = next(item for item in board.inventory if item.name == PLAIN)
        power = next(item for item in board.inventory if item.name == POWER)
        self.assertEqual((plain.count, power.count), (27, 28))
        self.assertEqual(policy.fixed_quest_readiness_state()["strategy_force"]["failed"],
                         ["throwing_items.launcher_ammo"])
        # Row 11 (1851/1700) sheds the surplus, the second digger 'n' among
        # it, and no bolt (recorded: the equipment deposit 'dk').
        self.assertEqual(policy._inventory_weight(board), 1851)
        self.assertTrue(board.inventory[ord("n") - ord("a")].name.startswith(DWARVEN_PICK))
        self.assertEqual((key, policy.last_reason),
                         ("dndldkda1\r\x1b", "home:weight-overload-deposit"))


        # DECLARED CONSTRUCTED: the Home of row 11 with its entrance; the
        # outside board is row 11's board without the store page.
        page = self.raw(11)
        game, current, reasons = self.drive(policy, board, key, page, self.home_shelf(),
                                            stop="shop:")
        self.assertEqual(reasons[0][1], "shop:approach", reasons)
        carried = {item["name"]: item["count"] for item in game.pack}
        self.assertEqual((carried[PLAIN], carried[POWER]), (27, 28))
        home = [item["name"] for item in game._items()]
        self.assertTrue(any(name.startswith(DWARVEN_PICK) for name in home), reasons)
        self.assertFalse(any(name.startswith(DWARVEN_PICK) for name in carried))
        self.assertFalse(policy._inventory_overweight(current))

    def test_home_take_under_the_limit_fills_the_carry_and_q2_travel_starts(self):
        # The recorded take of row 27 ('5 pR18', home:atomic-withdraw) at
        # 1645/1700: both diggers carried, the take capped at what fitted
        # beside the second.  DECLARED: the arrival policy consumes the
        # responses of rows 0-19 undecided (the seek-shelter divergence of
        # rows 3-7 is not this pin), then decides rows 20-26 with each
        # recorded key posted (rows 21, 23-25 differ: the take is bound at
        # row 21 and Home is travelled to at once).  With the fit left as it
        # was, row 27 reproduces the recorded '5 pR18'.
        policy = self.restore()
        for row in range(20):
            self.consume(policy, row)
        for row in range(20, 27):
            self.decide(policy, row)
            self.post(policy, self.journal[row]["key"])
        board, key = self.decide(policy, 27)
        self.assertFalse(policy._inventory_overweight(board))
        self.assertEqual(policy._inventory_weight(board), 1645)
        diggers = [item.name for item in board.inventory if item.is_digging_tool]
        self.assertEqual(len(diggers), 2)
        self.assertEqual(self.journal[27]["key"], "5 pR18\r\x1b")
        self.assertEqual((key, policy.last_reason), ("5 pR44\r\x1b", "home:atomic-withdraw"))

        # DECLARED CONSTRUCTED: the Home of row 27 is its ~9 catalogue of
        # row 25 (page 1 checked against the recorded page of row 26); the
        # take is posted from the entrance (row 27's board).
        knowledge = next(json.loads(line) for line in self.journal[25]["inputs"]
                         if '"knowledge"' in line)["knowledge"]["items"]
        shelf = [{k: v for k, v in item.items() if k != "slot"} for item in knowledge]
        recorded_page = self.raw(26)["store"]
        self.assertEqual([item["name"] for item in shelf[:52]],
                         [item["name"] for item in recorded_page["items"]])
        self.assertEqual(len(shelf), recorded_page["stock_num"])
        game, current, reasons = self.drive(policy, board, key, self.raw(27), shelf,
                                            stop="fixedquest:", inside=False,
                                            capacity=recorded_page["capacity"])
        # The take fills the carry to 99 (Home before purchase, owner
        # 2026-09-14); over the limit the relief shelves the surplus digger,
        # never a bolt; Q2's travel starts.
        self.assertEqual(reasons[-1][1], "fixedquest:q2-travel", reasons)
        carried = {item["name"]: item["count"] for item in game.pack}
        self.assertEqual((carried[PLAIN], carried[POWER]), (27 + 44, 28))
        home = [item["name"] for item in game._items()]
        self.assertTrue(any(name.startswith(DWARVEN_PICK) for name in home), reasons)
        self.assertLessEqual(policy._inventory_weight(current),
                             policy._inventory_weight_limit(current))
        readiness = policy.fixed_quest_readiness_state()
        self.assertEqual(readiness["strategy_force"]["carries"]
                         ["throwing_items.launcher_ammo"]["measured"], 99)
        self.assertEqual(readiness["strategy_force"]["failed"], [], readiness)

    def drive(self, policy, board, key, page, shelf, *, stop, inside=True, capacity=None):
        """Post each decided key through the production executor into the
        constructed Home until a decision's reason starts with ``stop``."""
        outside = copy.deepcopy(page)
        outside.pop("store", None)
        outside["type"] = "player_turn"
        outside["grid_map"] = self.raw(10)["grid_map"]
        game = MergingHomeGame(
            pack=copy.deepcopy(page["inventory"]),
            equipment={item["slot"]: item for item in copy.deepcopy(page["equipment"])},
            pages=[shelf[:52], shelf[52:]], inside=inside, state_template=outside,
            home_limit=capacity or page["store"]["capacity"])
        game.entrance = game.position = (page["player"]["y"], page["player"]["x"])
        game.turn = page["turn"]
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 5).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=policy)
        reasons = []
        current = board
        for _ in range(8):
            _send_new_decision_key(
                port, json.dumps(game._state()), key, None, set(),
                in_store=current.store is not None, snapshot=current,
                decision={"sequence": policy._decision_sequence,
                          "reason": policy.last_reason, "key": key})
            self.assertEqual(port.last_result.outcome, "completed",
                             (reasons, port.last_result.reason))
            self.post(policy, key)
            current = parse_snapshot(port.last_result.board, policy._monrace_knowledge)
            key = policy.choose_key(current)
            reasons.append((key, policy.last_reason))
            if policy.last_reason.startswith(stop):
                break
        return game, current, reasons


if __name__ == "__main__":
    unittest.main()
