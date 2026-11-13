"""n1-a life-522, Angband 24F, RANDOM quest 41 (target race 948), 2026-11-14 05:05-05:34.

The runner stopped the bot with ``stall:floor-dwell:quest-search:loop`` at 05:34:12: 29 minutes of
``quest-search:loop`` over the 76 cells x 74-107 east of a corridor of traps.  At 05:05:20 the bot
had walked east onto traps it had not seen ((40,71), (38,72), (38,73): three went off); known, they
walled the rest of the floor off from the search's walks, which keep off a known trap.  Restarted,
the bot's explore disarmed them (``D4``) and killed the target on the far side 5 seconds later.

Two roots, against the owner's rules for the random quest search (2026-11-08: the walk covers the
whole floor, a cut-off floor is opened first, and the floor is given up after two whole coverages):

1. The ground past a known trap was never opened (quest_target_search ``_past_traps``): the lap
   circled the pocket.  Now the enclosure ladder's disarm opener walks across the trap
   (retreat_enclosure ``cross_toward_key``, owner 2026-11-06 「罠の解除」).
2. The Staff of Detect Evil (10 charges, picked up at 05:01:34) spent its last charge at 05:03:04;
   the empty staff still counted as a held means (``held_cast_radius`` 30), so the walk's view
   counted for nothing and no cast came: no coverage could ever complete and the floor could never
   be given up.  Now a staff without a charge is no means, and the seen grids count (owner
   2026-11-08 21:5x 「感知の手段が無ければ、目で見えたマスを数える」).

Recorded: tests/fixtures/n1a-522-quest-search-1114.json.gz
(tests/extract_n1a_522_quest_search_1114_fixture.py): the capture's 114 boards and decision rows.
DECLARED CONSTRUCTED: the bot's remembered terrain of the floor from the floor's map checkpoint
(map-left-1-24-41.txt) installed as known and marked, and every floor cell written off as a probed
frontier (the recorded ``map_memory``: 3,250 known cells, all marked, no open frontier: explore
answered nothing on these boards).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import hengbot.policy  # noqa: F401 -- loads the modules in their cycle-safe order
from hengbot import quest_target_search as search
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.exploration_ledger import ExplorationLedger
from hengbot.model import Position, parse_snapshot
from tests.support import recorded
from tests.support.recorded import FaithfulHookGame, _policy, command_screen
from tests.test_n1b_348_stops_1108_recorded import knowledge

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-522-quest-search-1114.json.gz"
TRAPS = {Position(38, 71), Position(38, 72), Position(38, 73), Position(40, 71)}
WEST_END = 1338916  # the recorded board at (38,74), beside the trap (38,73): the lap turned back
DISARM = "stuck:walled-off-disarm"
DETECT_EVIL = (55, 15)  # tval, sval: 邪悪存在感知の杖, slot r


class N1a522QuestSearchRecordedTest(recorded.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.case = json.loads(gzip.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = knowledge(cls.case)
        cls.rows = {row["turn"]: row for row in cls.case["rows"]}

    def board(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.races)

    def policy(self, until):
        """The recorded boards up to ``until`` primed in order, and the declared terrain."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.races)
        ledger = ExplorationLedger(None)
        ledger.bind(self.board(self.case["rows"][0]))
        policy._exploration_ledger = ledger
        for raw in self.case["rows"]:
            if raw["turn"] > until:
                break
            policy.prime(self.board(raw))
        terrain = self.case["terrain"]
        cells = set()
        for name in ("floor", "wall", "door", "rubble"):
            each = {tuple(cell) for cell in terrain[f"{name}_t"]}
            getattr(policy, f"_remembered_{name}_t").update(each)
            cells |= each
        policy._remembered_known_t.update(cells)
        policy._remembered_marked_t.update(cells)
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        # No open frontier (the recorded map_memory): every floor cell is written off as probed.
        ledger.probed_frontiers |= {Position(y, x) for y, x in policy._floor_t | policy._remembered_floor_t}
        recorded.skill(policy, self.rows[until])
        return policy

    def decide(self, policy, raw):
        key = policy.choose_key(self.board(raw))
        return "" if key is None else str(key)

    # -- the recording -------------------------------------------------------

    def test_recorded_scene(self):
        last = self.board(self.case["rows"][-1])
        self.assertEqual(last.floor_key, (1, 24, 41))
        self.assertNotIn("telepathy", last.player.abilities)
        staff = next(item for item in last.inventory if (item.tval, item.sval) == DETECT_EVIL)
        self.assertEqual((staff.name, staff.charges), ("邪悪存在感知の杖 (0回分)", 0))
        self.assertEqual({grid.position for grid in last.grids.values() if grid.trap}, TRAPS)
        rows = self.case["decisions"]
        lap = [row for row in rows if row["reason"] == search.LOOP_REASON]
        self.assertEqual(len(lap), len(rows) - 1)  # and one survival:mana-absorb
        self.assertEqual(min(row["position"]["x"] for row in lap), 74)
        self.assertEqual(max(row["position"]["x"] for row in lap), 107)
        west = next(row for row in rows if row["turn"] == WEST_END)
        self.assertEqual((west["position"], west["key"]), ({"y": 38, "x": 74}, "6"))

    # -- 1. the ground past the traps ----------------------------------------

    def test_the_search_crosses_the_trap_toward_the_rest_of_the_floor(self):
        policy = self.policy(WEST_END)
        raw = self.rows[WEST_END]
        key = self.decide(policy, raw)
        self.assertEqual((key, policy.last_reason), ("D4", DISARM))
        board = self.board(raw)
        routes = search._routes(policy, board)
        self.assertEqual(len(routes), 76)
        self.assertGreater(len(search._past_traps(policy, board, routes, search._avoided(policy, board))),
                           100)
        # The key the production executor posts.
        following = next(row for row in self.case["rows"] if row["turn"] > WEST_END)
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [command_screen(following["turn"])]
        game.states = [copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                             "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        self.assertEqual("".join(game.accepted), key)

    # -- 2. the empty staff --------------------------------------------------

    def test_an_empty_staff_is_no_means_and_the_seen_grids_count(self):
        turn = self.case["rows"][-1]["turn"]
        policy = self.policy(turn)
        raw = self.rows[turn]
        self.decide(policy, raw)
        board = self.board(raw)
        self.assertTrue(search.searching(policy, board))
        self.assertEqual(search.held_cast_radius(policy, board), 0)
        self.assertTrue(search.no_means(policy, board))
        # The decision noted what the player's place shows toward the coverage: its own grid and
        # its neighbours (the boards carry no grid in view).
        memory = getattr(policy, search.MEMORY)
        self.assertIn((38, 76, 1), memory.sweeps.cover.centres)


if __name__ == "__main__":
    unittest.main()
