"""n1-c life-106 (Yeek cave 1F, 2026-11-02 16:18): two exits walked the player back and forth.

The floor was latched as a breeder breakthrough during a mining run, with
白イモムシの大群 (weak breeders) around the player.  Two up-stairs were
remembered: (27, 17), the nearer by distance, which remembered terrain does
not connect, and (56, 27), which it does.
  - No worm biting beside the player: the fundraising floor exit
    (``_finish_mining_floor``) routed to the reachable (56, 27), east.
  - A worm beside the player: survival preemption refused that exit, and the
    breakthrough's own exit routed only to the nearest stairs (27, 17); it
    found no route and walked to a frontier, west (decisions 14061, 14063).
The player moved between six cells until loop-detected.  Now the breakthrough
routes to the nearest stairs its remembered route reaches, so both exits walk
toward (56, 27).

Every decision goes through the public choose_key; the step is posted through
the production executor.  DECLARED RECONSTRUCTED: the remembered terrain, the
breakthrough latch and the fundraising mode are the capture's policy-state at
the stop (turn 1007980, 32 game turns after the first board); each board is
decided by a fresh policy (the capture keeps no frontier memory of the live
process, so the fresh frontier step differs from the recorded '4', while the
reason shows the exit that answered).  The board after the step is the
recorded next board.
Fixture: tests/extract_breeder_reachable_upstairs_1102_fixture.py.
"""
import tests  # noqa: F401 -- isolate runtime files

import copy
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from tests.test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "breeder-reachable-upstairs-1102.json.gz"
SHA256 = "c3a0f3c34c02180dddba4fd57a15579693d33ed1918ee1187516afa2142a1ecc"
TERRAIN_SETS = ("known", "marked", "floor", "wall", "door", "rubble")
BREAKTHROUGH_TO_STAIRS = {"breeder-breakthrough:seek-upstairs",
                          "breeder-breakthrough:clear-escape-path"}


class BreederReachableUpstairsRecordedTest(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        payload = FIXTURE.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == SHA256
        cls.data = json.loads(gzip.decompress(payload))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def decide(self, index):
        raw = copy.deepcopy(self.data["boards"][index])
        directory = Path(self.enterContext(TemporaryDirectory()))
        policy = _policy(directory, self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        # The captured process already held the skill list.
        policy.consume_skill_knowledge({
            "player": {"level": raw["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        terrain = self.data["terrain"]
        for name in TERRAIN_SETS:
            getattr(policy, f"_remembered_{name}_t").update(
                tuple(cell) for cell in terrain[f"{name}_t"])
        policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
        modes = self.data["modes"]
        policy._breeder_breakthrough_floor = tuple(modes["_breeder_breakthrough_floor"])
        policy._fundraising_mode = modes["_fundraising_mode"]
        policy._crossarea_fundraising_enforced = modes["_crossarea_fundraising_enforced"]
        _decoded, snapshots = _consume_response_sequence(
            [json.dumps(raw, ensure_ascii=False)], policy, lambda _key: True,
            self.monrace, knowledge_ledger_path=directory / "knowledge.jsonl")
        return policy, snapshots[-1], policy.choose_key(snapshots[-1])

    def test_recorded_exits_alternate(self):
        self.assertEqual(
            [(row["decision_sequence"], row["key"], row["reason"]) for row in self.data["decisions"]],
            [(14061, "4", "breeder-breakthrough:seek-frontier"),
             (14062, "6", "fundraise:seek-upstairs"),
             (14063, "4", "breeder-breakthrough:seek-frontier"),
             (14064, "4", "fundraise:seek-upstairs")])
        self.assertEqual(self.data["terrain"]["upstairs"], [[27, 17], [56, 27]])

    def test_biting_worm_board_walks_to_the_reachable_stairs(self):
        for index in (0, 2):
            with self.subTest(turn=self.data["boards"][index]["turn"]):
                policy, snapshot, key = self.decide(index)
                # 9afd9203e: breeder-breakthrough:seek-frontier (no route to (27, 17)).
                self.assertIn(policy.last_reason, BREAKTHROUGH_TO_STAIRS)
                self.assertEqual(policy._nearest_upstairs(snapshot), Position(27, 17))
                step = policy._breeder_breakthrough_step(snapshot)
                self.assertEqual(
                    policy._breeder_route_step(snapshot, snapshot.player.position,
                                               Position(56, 27)), step)
                self.assertEqual(key, "6")
        policy, _snapshot, key = self.decide(0)
        self.post(policy, self.data["boards"][0], key, self.data["boards"][1])

    def test_control_fundraising_exit_walks_the_same_way(self):
        policy, _snapshot, key = self.decide(1)
        self.assertEqual((key, policy.last_reason), ("6", "fundraise:seek-upstairs"))


if __name__ == "__main__":
    import unittest
    unittest.main()
