"""Boundary pins from the 2026-10-06 starvation incident on 694bbdfa.

These are recorded boards, not a lifetime replay. The state tail starts mid
process and contains two bot sessions. Each board is tested independently;
later historical boards are not asserted to result from our changed command.
The supplier boundary adopts the last recorded Home and skill knowledge.
The no-wait boundary supplies the unsanctioned WAIT this final safety rewrite
receives, with no observed HP loss (all seven boards have full HP). No hunt,
route, threat, inventory, scroll or safety producer is mocked.
"""
from __future__ import annotations

import tests  # noqa: F401 -- isolate live runtime files
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import STORE_MAGIC, _parse_items, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, WAIT_KEY

FIXTURE = Path(__file__).parent / "fixtures/starving-town-20261006.json.gz"
SHA256 = "c94fac65db2a4c7f1046126d45a155780ca620b05dbb3a566035e14f8d8ac68c"


class StarvingTownRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == SHA256
        cls.pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        cls.monrace = load_monrace_knowledge(
            Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc")
        )

    def boundary(self, pin):
        board = parse_snapshot(pin["board"], self.monrace)
        decision = pin["decision"]
        self.assertEqual(board.turn, decision["turn"])
        self.assertEqual(board.player.position.y, decision["position"]["y"])
        self.assertEqual(board.player.position.x, decision["position"]["x"])
        self.assertEqual(board.player.hp, decision["player"]["hp"])
        self.assertEqual(board.player.food_state, decision["player"]["food_state"])
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy._build_grid_index(board)
        return policy, board

    def supplier_boundary(self, pin):
        policy, board = self.boundary(pin)
        policy._observe(board)
        policy.consume_skill_knowledge(pin["knowledge"]["skill_exp"])
        policy.consume_home_knowledge(tuple(_parse_items(
            pin["knowledge"]["home"]["knowledge"]["items"],
            protocol=board.protocol_version,
        )))
        self.assertTrue(policy._home_knowledge_current)
        self.assertIsNone(policy._home_mana_food_candidate())
        return policy, board

    def test_supplier_travel_outvotes_recorded_hunt(self):
        for pin in self.pins[7:]:
            with self.subTest(decision_index=pin["decision_index"]):
                policy, board = self.supplier_boundary(pin)
                self.assertEqual(pin["decision"]["reason"], "town:kill-mob-approach")
                self.assertIn(board.player.food_state, {"hungry", "fainting"})
                self.assertTrue(board.in_town)
                self.assertIsNone(policy._find_edible(board))
                if "home_procurement_fallthrough" in pin["decision"]:
                    self.assertEqual(
                        pin["decision"]["home_procurement_fallthrough"]["case"],
                        "fresh-catalogue-absence",
                    )
                key = policy._mana_food_survival_override_key(board)
                self.assertEqual((key, policy.last_reason),
                                 ("\x1b`n&.", "survival:mana-shop-travel"))

    def test_public_boundary_keeps_supplier_priority(self):
        policy, board = self.supplier_boundary(self.pins[-1])
        self.assertEqual(policy.choose_key(board), "\x1b`n&.")
        self.assertEqual(policy.last_reason, "survival:mana-shop-travel")

    def test_food_interrupt_preserves_last_known_hunt_for_return(self):
        policy, board = self.supplier_boundary(self.pins[-1])
        # DECLARED CONSTRUCTED: the recorded monster just left sight; retain
        # the cell already observed on this board as the interrupted hunt.
        target = board.visible_monsters[0].position
        policy._town_hunt_target = target
        grids = {p: replace(g, has_monster=False, monster_index=0)
                 for p, g in board.grids.items()}
        board = replace(board, grids=grids, visible_monsters=[], detected_monsters=[])
        policy._build_grid_index(board)
        self.assertEqual(policy._mana_food_survival_override_key(board), "\x1b`n&.")
        self.assertEqual(policy._town_hunt_target, target)
        # DECLARED CONSTRUCTED: hand-feeding relieves hunger on this same board.
        fed = replace(board, player=replace(board.player, food_state="normal"))
        self.assertEqual(policy._town_clear_traveler_key(fed), "7")
        self.assertEqual(policy.last_reason, "town:kill-mob-approach")

    def test_all_starvation_states_yield_to_supplier_route(self):
        for state in ("hungry", "weak", "fainting"):
            with self.subTest(food_state=state):
                policy, board = self.supplier_boundary(self.pins[-1])
                # DECLARED CONSTRUCTED: change only starvation stage.
                board = replace(board, player=replace(board.player, food_state=state))
                self.assertEqual(policy._mana_food_survival_override_key(board), "\x1b`n&.")
                self.assertEqual(policy.last_reason, "survival:mana-shop-travel")

    def test_supplier_walk_can_attack_an_actual_route_blocker(self):
        policy, board = self.supplier_boundary(self.pins[8])
        route = policy._shopping_approach_step(board, STORE_MAGIC, requester="survival")
        self.assertIsNotNone(route)
        # A walking continuation has already selected a legal next tile.
        step = min(
            (p for p in policy._walkable_neighbors(board, board.player.position)
             if board.grid_at(p) is not None and board.grid_at(p).passable),
            key=lambda p: p.distance_to(policy._shopping_approach_goal),
        )
        self.assertEqual(board.player.position.distance_to(step), 1)
        # DECLARED CONSTRUCTED: put the recorded hostile on the route's next
        # tile, and seed native travel's existing fallback after interruption.
        monster = replace(board.visible_monsters[0], position=step, distance=1)
        grids = dict(board.grids)
        grids[step] = replace(grids[step], has_monster=True)
        board = replace(board, grids=grids, visible_monsters=[monster])
        policy._build_grid_index(board)
        policy._town_travel_fallback = policy._shopping_approach_goal
        policy.last_reason = "survival:mana-shop-approach"
        key = policy._shopping_approach_key(board, step, "survival:mana-shop-travel")
        # Hengband's direction into a hostile is the ordinary melee attack.
        self.assertEqual(key, policy._direction_key(board.player.position, step))
        self.assertEqual(policy.last_reason, "survival:mana-shop-approach")

    def test_seven_recorded_full_hp_escapes_do_not_spend_a_scroll(self):
        escapes = self.pins[:7]
        self.assertEqual(len(escapes), 7)
        for pin in escapes:
            with self.subTest(decision_index=pin["decision_index"]):
                policy, board = self.boundary(pin)
                self.assertEqual(pin["decision"]["reason"], "no-wait:escape-scroll")
                self.assertEqual(pin["decision"]["key"], "re")
                self.assertEqual(board.player.hp, board.player.max_hp)
                self.assertLess(pin["decision"]["threat_prediction"]["total"],
                                board.player.max_hp * .1)
                self.assertIsNotNone(policy._escape_scroll(board))
                hostiles = policy._physical_hostiles(board)
                self.assertGreater(policy._predicted_damage(board, hostiles, 3), 0)
                policy.last_reason = "town:blocked:repetition"
                key = policy._forbid_wait_while_damaged(board, WAIT_KEY)
                self.assertNotEqual(key, "re")
                self.assertNotEqual(policy.last_reason, "no-wait:escape-scroll")
                self.assertNotEqual(key, WAIT_KEY)

    def test_low_hp_still_allows_escape_on_recorded_fire_vortex_board(self):
        policy, board = self.boundary(self.pins[0])
        # DECLARED CONSTRUCTED: lower only HP to just below the user's threshold.
        board = replace(board, player=replace(
            board.player,
            hp=int(policy._low_hp_walk_threshold(board.player.max_hp)) - 1,
        ))
        policy.last_reason = "town:blocked:repetition"
        self.assertEqual(policy._forbid_wait_while_damaged(board, WAIT_KEY), "re")
        self.assertEqual(policy.last_reason, "no-wait:escape-scroll")

    def test_material_prediction_at_full_hp_still_allows_escape(self):
        policy, board = self.boundary(self.pins[0])
        # DECLARED CONSTRUCTED: eight copies of the recorded ranged attacker.
        monster = board.visible_monsters[0]
        board = replace(board, visible_monsters=[
            replace(monster, index=100 + i) for i in range(8)
        ])
        self.assertGreaterEqual(
            policy._predicted_damage(board, policy._physical_hostiles(board), 3),
            board.player.max_hp * .1,
        )
        policy.last_reason = "town:blocked:repetition"
        self.assertEqual(policy._forbid_wait_while_damaged(board, WAIT_KEY), "re")
        self.assertEqual(policy.last_reason, "no-wait:escape-scroll")

    def test_material_unseen_loss_threshold_does_not_bypass_scroll_gate(self):
        for loss, escapes in ((106, False), (107, True)):
            with self.subTest(loss=loss):
                policy, board = self.boundary(self.pins[0])
                # DECLARED CONSTRUCTED: unseen fire on a dungeon floor, full HP
                # after healing, with a retained single-move observed loss.
                board = replace(board, floor_key=(1, 1, 0), town_flag=False,
                                visible_monsters=[], detected_monsters=[])
                policy._took_damage = True
                policy._last_damage_amount = loss
                policy.last_reason = "combat:disengage-wait"
                key = policy._forbid_wait_while_damaged(board, WAIT_KEY)
                self.assertEqual(key == "re", escapes)
                self.assertEqual(policy.last_reason == "no-wait:escape-scroll", escapes)


if __name__ == "__main__":
    unittest.main()
