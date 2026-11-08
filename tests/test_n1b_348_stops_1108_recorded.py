"""n1-b (Magic-Eater) life-348 2026-11-08: a town stop and a dungeon loop.

Recorded: tests/fixtures/n1b-348-stops-1108/ (tests/extract_n1b_348_stops_1108_fixtures.py),
build bot-206702cc9.  Every decision is the public ``choose_key``; the asserted keys go
through the production executor port.

A, 15:16 town:blocked:owner-retired-burst: the Magic-Eater's spare *Identify* filed a Home
take of 耐電のアミュレット (me_powerful_activation ``_home_take_key``, the catalogue take of
home_identification) on an earlier visit.  The item's name then changed: Home and the
equipment catalogue list 耐電のアミュレット {r電} x9, fully known.  The take stayed filed
(home_identification ``release_stale_take`` kept a take with no other candidate), so the
open Home page handed it off to the entrance (policy.py home:leave-for-pending-withdraw,
``_bound_home_take_signatures``), the entrance found it unobserved and stepped off
(policy_home ``_atomic_home_withdraw_dispatch_key`` home-errand:target-unobserved), the
wait re-entered Home, until the owner-retired burst.  Now a take whose name nothing in the
catalogue or the current Home catalogue carries gives way at once.

B, 14:37 loop-detected (Orc cave 23F): a sleeping ダークエルフ・ロード (race 348) lay at
[23,73].  At [23,79] (distance 6) it was in view and ``threat:avoid-engagement`` stepped '9'
to [22,80] (owner 2026-11-07 「眠っている敵でも強い敵からは離れる」); there the wall hid it,
``_engagement_danger_cells`` (monsters in view only) was empty, and the explore stepped '1'
straight back, 40 times until the loop detector.  The retreat's veto of [23,79] was not
claimed because every remembered frontier lay past the sleeper (engagement_avoid_seal).
Now a sleeper out of sight is judged at its last shown cell (sleeper_reach_memory).
DECLARED RECONSTRUCTION: a fresh policy decides the capture's first board ([23,79], the
sleeper in view).  DECLARED COUNTERFACTUAL (the walk): from the next board ([22,80], out of
sight) the player follows the decided moves with nothing in view, ten game turns a decision,
for the retreat veto's window; the remembered frontiers beyond the sleeper's area are taken
as already probed, so the frontiers left lie past it, where the live explore went.

Receipts (both stops' bot-stderr.log are full of town:blocked:work-contract:unmapped-
producer; the life's town-work-receipts.jsonl holds 11,486 of them, 99% at the executor-post
seam, with the driver-submit receipt of the same key valid): an operation's completion set
the executor's ready board but kept the screen/state bound by the last _observe_decidable,
so after a recall every dungeon post was judged on the town state.  The same stale binding
made a backpressure retry after any completed operation a terminal ("prompt changed before
retry").  DECLARED CONSTRUCTED: the recorded town board (A row 3) is followed by the recorded
dungeon board (B, [22,80]) as if a recall had activated on a wait.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import itertools
import json
import lzma
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import PostingContract, SendResult, _ExecutorInputPort, _send_new_decision_key
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.home_errand import HomeErrandState
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import HUNT_RANGE
from hengbot.retreat_veto_life import UNSEEN_GAME_TURNS
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST)
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from tests import test_input_executor as executor_pins
from tests.test_dungeon_1031_recorded import RecordedHarness, decide
from town_work_corpus import replay_window

FIXTURES = Path(__file__).with_name("fixtures") / "n1b-348-stops-1108"
STALE_TAKE = ("耐電のアミュレット", 40, 30)
SHELVED = ("耐電のアミュレット {r電}", 40, 30)
with gzip.open(FIXTURES / "b.json.gz", "rt", encoding="utf-8") as _stream:
    LOOP = json.load(_stream)
RECORDED = {row["turn"]: (row["key"], row["reason"]) for row in LOOP["decisions"]}
AVOID = "threat:avoid-engagement"
SLEEPER, SLEEPER_RACE = Position(23, 73), 348
MOVES = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}


def knowledge():
    races = {}
    for race, facts in LOOP["monraces"].items():
        facts = copy.deepcopy(facts)
        for name in ("flags", "abilities"):
            facts[name] = frozenset(facts[name])
        facts["blows"] = tuple(MonsterBlow(**row) for row in facts["blows"])
        facts["names"] = tuple(facts["names"])
        races[int(race)] = MonraceKnowledge(**facts)
    return races


def here(raw):
    return Position(raw["player"]["y"], raw["player"]["x"])


class StaleCatalogueTakeRecordedTest(executor_pins.ProductionHarness):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        for name in ("runtime-env", "history-env", "runtime"):
            (self.scratch / name).mkdir()
        env = mock.patch.dict(os.environ, {
            RUNTIME_DIR_ENV: str(self.scratch / "runtime-env"),
            HOME_HISTORY_DIR_ENV: str(self.scratch / "history-env")})
        env.start()
        self.addCleanup(env.stop)

    def visit(self):
        """The fixture as a town-arrival directory replay_town_arrival reads."""
        source, visit = FIXTURES / "a", self.scratch / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((source / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((source / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        return visit

    def arrival(self):
        """The arrival policy and its journalled boards (as replay_town_arrival.replay)."""
        visit, runtime = self.visit(), self.scratch / "runtime"
        policy = restore(visit, runtime)
        calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
        if calibration.is_file():
            adopt_calibration(policy, calibration, runtime)
        return policy, decisions(policy, visit, runtime), journal(visit)

    def test_recorded_arrival_carries_a_take_whose_item_was_renamed(self):
        policy, _rows, _journal = self.arrival()
        errand = policy._home_errand
        self.assertEqual(errand.state, HomeErrandState.COMPOSABLE)
        self.assertEqual(errand.request.signature, STALE_TAKE)
        self.assertEqual(errand.request.purpose, "identification-catalog")
        catalogued = {policy._item_signature(owned.item): owned
                      for owned in policy._equipment_catalog.items}
        self.assertNotIn(STALE_TAKE, catalogued)
        self.assertTrue(catalogued[SHELVED].item.fully_known)
        self.assertIn(SHELVED, {policy._item_signature(item)
                                for item in policy._home_knowledge_items})

    def test_the_renamed_take_gives_way_and_no_home_hand_off_holds_it(self):
        policy, rows, entries = self.arrival()
        # Rows 0-2 (travel home, deposit, leave) decide as recorded.
        result = replay_window("n1b-348-a", policy, itertools.islice(rows, 3))
        self.assertEqual((result.matched_rows, result.first_divergence), (3, None))
        recorded, supply = next(rows)
        board = supply()
        key = policy.choose_key(board)
        # Recorded row 3 saved the game with the take still filed; the visit then
        # alternated Home and its entrance for it until the owner-retired burst.
        self.assertEqual(recorded["reason"], "periodic:game-save")
        self.assertFalse(policy._home_errand.active)
        self.assertNotIn(STALE_TAKE, policy._bound_home_take_signatures())
        self.assertFalse(policy.last_reason.startswith(("home:", "home-errand:")), policy.last_reason)
        raw = json.loads(entries[3]["line"] or entries[3]["inputs"][-1])
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [dict(raw, turn=raw["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)



class SleeperOutOfSightRecordedTest(RecordedHarness):
    def test_recorded_retreat_then_walk_back(self):
        seen, hidden = LOOP["boards"][0], LOOP["boards"][1]
        self.assertEqual(here(seen), Position(23, 79))
        self.assertEqual([(m["race_id"], m["y"], m["x"], m["asleep"]) for m in seen["visible_monsters"]],
                         [(SLEEPER_RACE, 23, 73, True)])
        self.assertEqual(RECORDED[seen["turn"]], ("9", AVOID))
        self.assertEqual(here(hidden), Position(22, 80))
        self.assertEqual(hidden["visible_monsters"], [])
        self.assertEqual(RECORDED[hidden["turn"]], ("1", "explore"))

    def test_out_of_sight_no_walk_goes_into_the_sleepers_reach(self):
        policy = HengbotPolicy(monrace_knowledge=knowledge())
        seen = copy.deepcopy(LOOP["boards"][0])
        policy.prime(parse_snapshot(copy.deepcopy(seen), policy._monrace_knowledge))
        key = decide(policy, copy.deepcopy(seen))
        self.assertEqual((key, policy.last_reason), ("9", AVOID))
        self.post(policy, seen, key, [], self.later(seen))
        policy.confirm_key_posted(key)
        raw = copy.deepcopy(LOOP["boards"][1])
        # DECLARED COUNTERFACTUAL (module docstring): only the frontiers past it left.
        board = policy._with_grid_memory(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        beyond = {Position(y, x) for y, x in policy._remembered_floor_t
                  if policy._is_remembered_frontier(board, Position(y, x))
                  and Position(y, x).distance_to(SLEEPER) > HUNT_RANGE}
        policy._probed_frontiers |= beyond
        policy._exploration_ledger.probed_frontiers |= beyond
        start, distance = raw["turn"], here(raw).distance_to(SLEEPER)
        reasons = []
        while raw["turn"] - start <= UNSEEN_GAME_TURNS:
            key = decide(policy, copy.deepcopy(raw))
            reasons.append(policy.last_reason)
            if key:
                policy.confirm_key_posted(key)
            if key not in MOVES and key not in {"s", "5"}:
                break
            raw["turn"] += 10
            raw["messages"] = []
            if key in MOVES:
                step = Position(here(raw).y + MOVES[key][0], here(raw).x + MOVES[key][1])
                self.assertGreaterEqual(step.distance_to(SLEEPER), distance,
                                        (raw["turn"], key, policy.last_reason))
                raw["player"]["y"], raw["player"]["x"] = step.y, step.x
        self.assertNotIn("explore", reasons)
        # The floor whose way on lies past it is left by the existing stuck escape.
        self.assertEqual(reasons[-1], "stuck:recall-escape")



def town_board():
    """A's recorded town board of row 3 (turn 3000391)."""
    rows = lzma.decompress((FIXTURES / "a" / "journal.jsonl.xz").read_bytes()).splitlines()
    entry = json.loads(rows[3])
    return json.loads(entry["line"] or entry["inputs"][-1])


class TownWorkReceiptsRecordedTest(executor_pins.ProductionHarness):
    def after_recall(self, faults=()):
        """The port and receipts of a dungeon post following a completed town wait."""
        town, dungeon = town_board(), copy.deepcopy(LOOP["boards"][1])
        game = executor_pins.FaithfulHookGame()
        game.state, game.screen = town, executor_pins.command_screen(town["turn"])
        _game, _client, executor = self.make(game)
        receipts = []
        executor.work_receipt = receipts.append
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        game.states, game.screens = [dungeon], [executor_pins.command_screen(dungeon["turn"])]
        self.assertEqual(port("5", decision={"reason": "town:wait-recall", "sequence": 1}),
                         SendResult.SENT)
        receipts.clear()
        game.faults = list(faults)
        following = dict(dungeon, turn=dungeon["turn"] + 10)
        game.states, game.screens = [following], [executor_pins.command_screen(following["turn"])]
        sent = port("6", decision={"reason": "explore", "sequence": 2})
        return sent, port, receipts

    def test_a_dungeon_post_after_a_recall_needs_no_town_work(self):
        sent, port, receipts = self.after_recall()
        self.assertEqual(sent, SendResult.SENT, port.last_result.reason)
        self.assertEqual([(r["seam"], r["required"], r["reason"]) for r in receipts],
                         [("executor-post", False, None)])

    def test_a_backpressure_retry_compares_with_the_completed_observation(self):
        # Refused once by backpressure, the sole retry compares the re-observed screen
        # and state with the ones the operation was admitted on (the completed one's).
        sent, port, _receipts = self.after_recall(faults=["backpressure"])
        self.assertEqual(sent, SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")


if __name__ == "__main__":
    unittest.main()
