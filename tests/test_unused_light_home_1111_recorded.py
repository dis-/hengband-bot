"""A light the departure does not use goes to Home (owner 2026-11-11).

「使わない光源を自宅に仕舞う処理を追加」, the light case of 2026-11-04
「使わない装備をキープしたままダンジョンに出発している。自宅に仕舞うようにしたい。」

n1-b life-370 (2026-11-11 23:30) wore ★知識の石 and carried
★ガラドリエルの玻璃瓶 and ★火消しライター on every departure: Home's spare-gear
shape (``_spare_equipment_deposit_shape``) left every light out.

* visit-233016: the visit's Home deposit (row 3) shelved three items and left
  both lights in the pack.
* next-233058: the next arrival, both lights still carried.

Recorded: each arrival checkpoint and its first journal rows
(tests/extract_unused_light_1111_fixture.py), decided through the public chooser.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import spare_gear
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.equipment_optimizer import Loadout, current_loadout, equipment_identity
from hengbot.equipment_transaction_planner import plan_equipment_transactions
from hengbot.model import STORE_HOME, SV_LITE_TORCH, TVAL_LITE, StoreState
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, restore
from tests.support.recorded import FaithfulHookGame, command_screen, store_screen
from tests.support import recorded as _executor_support

FIXTURES = Path(__file__).with_name("fixtures") / "unused-light-1111"
LEAF = "spare_gear_stowed"
PHIAL = "★ガラドリエルの玻璃瓶"
LIGHTER = "★火消しライター"


class Visit:
    def __init__(self, name):
        source = FIXTURES / name
        self._directory = TemporaryDirectory()
        root = Path(self._directory.name)
        scratch = root / "scratch"
        scratch.mkdir()
        visit = root / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(
            gzip.compress(lzma.decompress((source / "journal.jsonl.xz").read_bytes())))
        self.policy = restore(visit, scratch)
        self.rows = list(decisions(self.policy, visit, scratch))

    def close(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self._directory.cleanup()

    def post(self, key):
        self.policy.confirm_key_posted(key)
        chain = self.policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            self.policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def named(items, name):
    return next(item for item in items if name in item.name)


class UnusedLightHomeRecordedTest(_executor_support.ProductionHarness):
    def visit(self, name):
        visit = Visit(name)
        self.addCleanup(visit.close)
        return visit

    def test_home_shelves_both_unused_lights_through_the_executor(self):
        visit = self.visit("visit-233016")
        policy = visit.policy
        boards = []
        for recorded, supply in visit.rows[:3]:
            board = supply()
            boards.append(board)
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
            visit.post(key)
        recorded, supply = visit.rows[3]
        inside = supply()
        self.assertEqual(inside.store.store_type, STORE_HOME)
        worn = next(item for item in inside.equipment if item.is_light)
        self.assertIn("★知識の石", worn.name)
        phial, lighter = named(inside.inventory, PHIAL), named(inside.inventory, LIGHTER)
        # Recorded "dqdndg": three items shelved, both lights left in the pack.
        self.assertEqual((recorded["key"], recorded["reason"]),
                         ("dqdndg\x1b", "home:atomic-deposit"))
        key = policy.choose_key(inside)
        self.assertEqual(policy.last_reason, "home:atomic-deposit")
        self.assertEqual(key, "dqdpdodndg\x1b")
        self.assertEqual(key[1:-1:2], "qpong")
        self.assertIn(phial.slot, key[1:-1:2])
        self.assertIn(lighter.slot, key[1:-1:2])

        # DECLARED CONSTRUCTED: the game's replies (the Home page, then the map).
        game = FaithfulHookGame()
        home_state = self.store_state(inside.turn)
        home_state["store"]["store_type"] = STORE_HOME
        game.screens = [store_screen(), command_screen(inside.turn + 1)]
        game.states = [home_state, {"turn": inside.turn + 1, "grid_map": {"runs": []}}]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        posted = set()
        sent, _ = _send_new_decision_key(
            port, "home-entrance", "1", None, posted, in_store=False,
            decision={"sequence": 1, "reason": "shop:approach"},
            snapshot=boards[-1], posting_contract=PostingContract())
        self.assertTrue(sent)
        sent, _ = _send_new_decision_key(
            port, "home", key, None, posted, in_store=True,
            decision={"sequence": 2, "reason": policy.last_reason},
            snapshot=inside, posting_contract=PostingContract())
        self.assertTrue(sent)
        self.assertEqual(game.accepted, ["1", key])

    def test_departure_waits_for_home_while_a_light_is_carried(self):
        visit = self.visit("next-233058")
        policy = visit.policy
        board = visit.rows[0][1]()
        for name in (PHIAL, LIGHTER):
            self.assertTrue(spare_gear.released(policy, board, named(board.inventory, name)), name)
        self.assertTrue(spare_gear.stow_pending(policy, board))
        self.assertFalse(policy._town_departure_conjuncts(board, commit=False)[LEAF])

    def shelved(self, policy, board):
        """DECLARED CONSTRUCTED: the previous visit's deposit of both lights.

        The pack without them and the Home list (``~9``) with them, as the
        catalogue the arrival held plus the two pieces.
        """
        lights = tuple(item for item in board.inventory if item.name.startswith((PHIAL, LIGHTER)))
        self.assertEqual(len(lights), 2)
        home = tuple(owned.item for owned in policy._equipment_catalog.items
                     if owned.origin == "home")
        policy._equipment_catalog.complete_home_scan((*home, *lights))
        policy.consume_home_knowledge((*home, *lights))
        return replace(board, inventory=[item for item in board.inventory if item not in lights]), lights

    def test_next_visit_does_not_take_the_shelved_lights_back(self):
        visit = self.visit("next-233058")
        policy = visit.policy
        recorded, supply = visit.rows[0]
        board = supply()
        # Carried, both are the spare gear this rule shelves ...
        self.assertTrue(all(spare_gear.released(policy, board, item)
                            for item in board.inventory if item.is_light))
        after, lights = self.shelved(policy, board)
        # ... and shelved, nothing takes them back.  The recorded first
        # decision stands; nothing is left to shelve.
        key = policy.choose_key(after)
        self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
        self.assertFalse(spare_gear.stow_pending(policy, after))
        self.assertTrue(policy._town_departure_conjuncts(after, commit=False)[LEAF])
        deposit = policy._find_home_deposit(after)
        self.assertFalse(deposit is not None and deposit.is_light)
        # No light rule asks for them: the worn ★知識の石 outranks both.
        self.assertIsNone(policy._light_to_wield(after))
        self.assertFalse(any("light" in need.category or "lantern" in need.category
                             for need in policy._town_need_candidates(after)))
        # The Home catalogue still offers both to the loadout search.
        home_lights = {owned.item.name for owned in policy._equipment_catalog.items
                       if owned.origin == "home" and owned.item.is_light}
        self.assertTrue({light.name for light in lights} <= home_lights)

    def test_a_better_home_light_is_withdrawn_and_then_kept(self):
        visit = self.visit("next-233058")
        policy = visit.policy
        board = visit.rows[0][1]()
        after, _lights = self.shelved(policy, board)
        policy._equipment_catalog.refresh_carried(after.inventory, after.equipment)
        catalog = policy._equipment_catalog.items
        current = current_loadout(catalog)
        phial = next(owned for owned in catalog if owned.origin == "home" and PHIAL in owned.item.name)
        # DECLARED CONSTRUCTED: an optimizer target that wears the Home phial.
        target = Loadout(tuple((slot, phial if slot == "light" else owned)
                               for slot, owned in current.slots), current.hand_mode)
        plan = plan_equipment_transactions(
            catalog, current, target, current_pack_items=len(after.inventory),
            home_scan_complete=True)
        self.assertIn(("withdraw", equipment_identity(phial.item)),
                      [(action.kind, action.item_identity) for action in plan.actions])
        # Withdrawn (the recorded board carries it), the chosen phial stays in
        # the pack; the dark lighter is still spare.
        policy._equipment_optimization_preparation = SimpleNamespace(
            # TEST_FAKERY_LINT_ALLOW: pipeline-result-injected: the optimizer's chosen light is the given input; the spare-gear release of the pack lights is the subject
            result=SimpleNamespace(best=SimpleNamespace(loadout=target)))
        self.assertFalse(spare_gear.released(policy, board, named(board.inventory, PHIAL)))
        self.assertTrue(spare_gear.released(policy, board, named(board.inventory, LIGHTER)))

    def test_deliberate_spare_lights_stay_carried(self):
        visit = self.visit("next-233058")
        policy = visit.policy
        board = visit.rows[0][1]()
        phial = named(board.inventory, PHIAL)
        worn = next(item for item in board.equipment if item.is_light)
        self.assertTrue(spare_gear.released(policy, board, phial))
        # DECLARED CONSTRUCTED: each board below changes one recorded fact.
        torch = replace(worn, name="松明(2500ターンの寿命)", sval=SV_LITE_TORCH, fuel=2500,
                        known_flags=frozenset(), is_artifact=False, artifact_id=0)
        cases = {
            # A worn fuel light: the carried permanent light is its spare.
            "worn-torch": (replace(board, equipment=[torch if item is worn else item
                                                     for item in board.equipment]), phial),
            # No worn light: the light wield takes it from the pack.
            "no-worn-light": (replace(board, equipment=[item for item in board.equipment
                                                        if item is not worn]), phial),
            # An unidentified light: the identification flow owns it.
            "unidentified": (board, replace(phial, known=False)),
            # Torches: the torch carry and the General Store sale own them.
            "carried-torch": (board, replace(torch, slot=phial.slot)),
        }
        for case, (snapshot, light) in cases.items():
            with self.subTest(case):
                self.assertEqual(light.tval, TVAL_LITE)
                self.assertFalse(spare_gear.released(policy, snapshot, light))
        # A planned mining run keeps its light.
        policy._fundraising_mode = "prepare"
        self.assertFalse(spare_gear.released(policy, board, phial))


if __name__ == "__main__":
    unittest.main()
