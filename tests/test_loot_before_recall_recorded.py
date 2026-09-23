"""Pins: a calm return collects the visible loot before reading the recall.

Live incident: Forest 24F, floor (7, 24, 0), 2026-09-23 20:10:13-20:10:14,
protocol 3, decisions 5384-5386 of one bot process.  An emergency teleport
('rf') relocated the player to (38, 55); the unique 悪鬼の血脈『ティボルト』
followed, was killed by the next melee ('8'), and dropped at (37, 55).  On the
board that followed, decision 5386 read Word of Recall ('rg') with hp 444/592,
zero visible hostiles, ``threat_prediction.total`` zero and SEVEN items on the
floor -- three of them at (38, 55) under the player, (37, 55) and (37, 56)
beside it.  The user's report: 「ユニークを倒してドロップ未回収で帰還」.

User decision 2026-09-23 (topic loot-before-recall), verbatim:
「見えている分は全部拾う」 -- after the return/recall trigger has fired, if no
hostile is visible and the threat prediction is zero, the bot collects EVERY
loot item it can see on the floor before reading the Word of Recall.  If danger
returns it goes straight back to the return/survival behaviour.  Loot it cannot
reach before the recall activates is abandoned; the activation itself is NOT
cancelled.

Why the recall outranked the loot: the return owner (_return_to_town_key) runs
in _decide above the ordinary loot owner, and the ordinary loot owner is itself
closed while ``_emergency_return_active``.  The only loot opportunity above the
return was the routine sweep, which required ``_last_return_trigger`` to be one
of RETURN_LOOT_SWEEP_TRIGGERS and the emergency latch to be clear; the live
trigger was ``emergency-material-threat`` with the latch set, so both gates
failed and the return read the scroll on top of the drop.

``loot.blocker == "navigation-ledger:loot"`` is the NavigationLedger expiry: a
committed loot target whose best distance stopped improving for
NAV_TARGET_STALL_LIMIT decisions is deferred for the floor visit.  The flight
that preceded this board guarantees that plateau, so the fix hands those
positions one fresh budget when the calm return begins; each position is
released at most once per floor visit and expires again on its own if it still
cannot be approached.

The unique's drop is NOT distinguishable in the data: every one of the seven
entries is an ``object_count`` on a grid, with no owner, no kill and no
identity.  It is collected because it is visible floor loot, not because a
unique died on it.

Substrate: tests/fixtures/loot-before-recall-20260923.jsonl.gz, frozen by
tests/extract_loot_before_recall_fixture.py at decision boundaries taken from
``timing.jsonl_drain_records`` (see the .provenance.txt beside it).  It carries
decisions 5280-5386 with the board each one decided on, plus the recorded ``~f``
skill list of the same character and run.

Replay fidelity: a restarted policy fed the frozen boards reproduces the
recorded REASON of all 107 decisions and the recorded (reason, key) of the last
seven before the incident decision; the earlier exploration keys differ because
a restart has no visit history.  On decision 5386 the restart reproduced the
recorded ``return:recall`` 'rg' exactly before this fix, which is what makes the
substrate able to tell the fix from its absence.

Walls: tests/__init__ runtime-file isolation only; every board is a dungeon
floor, so no Home/town/shop producer with a file of its own is reached.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import gzip
import hashlib
import json
import re
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import RETURN_LOOT_SWEEP_CRITICAL_TRIGGERS, HengbotPolicy


FIXTURE = (
    Path(__file__).parent / "fixtures" / "loot-before-recall-20260923.jsonl.gz"
)
FIXTURE_SHA256 = "2f4329b3ceafe7d52863ae064f5dcd5868f1a3a4eb2c9308651c17ef9b629262"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")
INCIDENT = 5386  # the decision that read the recall on top of the drop
UNDERFOOT = Position(38, 55)  # the item the player stood on
BESIDE = (Position(37, 55), Position(37, 56))  # the unique's drop and its neighbour
UNREACHABLE = (  # visible, but no route through the remembered map
    Position(25, 69),
    Position(26, 62),
    Position(26, 69),
    Position(27, 69),
)
MOVES = {
    "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
    "4": (0, -1), "6": (0, 1),
    "1": (1, -1), "2": (1, 0), "3": (1, 1),
}


class LootBeforeRecallRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        cls.skill = next(r for r in records if r["role"] == "skill-knowledge")["board"]
        cls.inputs = [r for r in records if r["role"] == "decision-input"]
        cls.monrace = load_monrace_knowledge(MONRACES)

    def _replay_to_incident(self):
        """Replay the frozen decisions up to (not including) the incident board."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        # The live process read its ~f list long before this window; a restart
        # consumes the recorded response through the same public entry point
        # the client uses, so no board here opens on the request.
        policy.consume_skill_knowledge(self.skill)
        replayed = []
        for record in self.inputs[:-1]:
            snapshot = parse_snapshot(record["board"], self.monrace)
            key = policy.choose_key(snapshot)
            replayed.append((record["decision"], policy.last_reason, key))
        incident = self.inputs[-1]
        self.assertEqual(incident["decision"]["decision_sequence"], INCIDENT)
        return policy, replayed, parse_snapshot(incident["board"], self.monrace)

    def _routable(self, policy, snapshot, positions):
        return [
            position
            for position in positions
            if policy._position_target_step(snapshot, position) is not None
        ]

    def test_substrate_reproduces_the_recorded_run(self):
        """The frozen boards are the live decisions, not a re-derived story."""
        policy, replayed, incident = self._replay_to_incident()
        self.assertEqual(len(replayed) + 1, 107)
        self.assertEqual(
            [record["reason"] for record, _reason, _key in replayed],
            [reason for _record, reason, _key in replayed],
        )
        self.assertEqual(
            [(reason, key) for _record, reason, key in replayed[-7:]],
            [
                (record["reason"], record["key"])
                for record, _reason, _key in replayed[-7:]
            ],
        )
        # The board the incident decision saw is the recorded one.
        self.assertEqual(incident.floor_key, (7, 24, 0))
        self.assertEqual(incident.player.position, UNDERFOOT)
        self.assertEqual(incident.player.hp, 444)
        self.assertEqual([m for m in incident.visible_monsters if m.hostile], [])
        self.assertEqual([m for m in incident.detected_monsters if m.hostile], [])
        state = policy.loot_state(incident)
        self.assertEqual(len(state["visible"]), 7)
        self.assertEqual(
            {(item["position"]["y"], item["position"]["x"]) for item in state["visible"]},
            {(position.y, position.x) for position in (UNDERFOOT, *BESIDE, *UNREACHABLE)},
        )
        # The same quantity the decision log printed as threat_prediction.total.
        self.assertEqual(
            policy.threat_prediction(
                incident,
                [m for m in incident.visible_monsters if m.hostile],
            )["total"],
            0,
        )
        # The return that fired is the emergency one the routine sweep excludes.
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "emergency-material-threat")
        self.assertTrue(policy._emergency_return_active)

    def test_l1_calm_return_collects_the_drop_instead_of_reading_the_recall(self):
        """L1: the recorded board no longer spends its decision on the scroll."""
        policy, _replayed, incident = self._replay_to_incident()
        # The ledger blocker was live on this board, exactly as recorded.
        self.assertEqual(policy._loot_defer_blocker, "navigation-ledger:loot")
        blocked = set(policy._nav_ledger_deferred_loot)
        self.assertTrue(blocked)
        self.assertTrue(blocked <= set(policy._deferred_loot))

        key = policy.choose_key(incident)

        self.assertNotEqual(policy.last_reason, "return:recall")
        self.assertNotEqual(key, "rg")
        # The loot owner took the decision: the item underfoot is picked up
        # through the existing step-off that makes the game run its own floor
        # handling on re-entry (_current_floor_item_key, position unchanged).
        self.assertEqual(policy.last_reason, "trigger-autodestroy")
        self.assertEqual(key, "7")
        # The navigation-ledger deferral that would otherwise suppress the
        # collection was released, once, and the blocker cleared with it.
        self.assertEqual(policy._loot_ledger_rearmed, blocked)
        self.assertEqual(policy._nav_ledger_deferred_loot, set())
        self.assertFalse(blocked & policy._deferred_loot)
        self.assertIsNone(policy.loot_state(incident)["blocker"])

    def test_l2_a_visible_hostile_reads_the_recall_exactly_as_recorded(self):
        """L2: the gate closes on any visible hostile; the return is unchanged."""
        policy, _replayed, incident = self._replay_to_incident()
        # A hostile recorded on this run (古代の死霊, race 128) standing on a
        # known cell of this same board, far enough that no combat owner claims
        # the decision -- the only difference from L1 is that it is visible.
        ghoul = self._recorded_ghoul()
        board = replace(
            incident,
            visible_monsters=[
                replace(ghoul, position=Position(33, 62), distance=7, asleep=True)
            ],
        )
        self.assertFalse(policy._loot_before_recall_calm(board))

        key = policy.choose_key(board)

        self.assertEqual(policy.last_reason, "return:recall")
        self.assertEqual(key, "rg")
        self.assertEqual(policy._loot_ledger_rearmed, set())

    def test_l3_a_nonzero_threat_prediction_reads_the_recall(self):
        """L3: no visible hostile, but the prediction is not zero."""
        policy, _replayed, incident = self._replay_to_incident()
        ghoul = self._recorded_ghoul()
        board = replace(
            incident,
            detected_monsters=[
                replace(ghoul, position=Position(36, 56), distance=2, asleep=True)
            ],
        )
        self.assertEqual([m for m in board.visible_monsters if m.hostile], [])
        self.assertEqual(
            policy.threat_prediction(board, board.detected_monsters)["total"], 18
        )
        self.assertFalse(policy._loot_before_recall_calm(board))

        key = policy.choose_key(board)

        self.assertEqual(policy.last_reason, "return:recall")
        self.assertEqual(key, "rg")
        self.assertEqual(policy._loot_ledger_rearmed, set())

    def test_l4_every_reachable_item_is_collected_nearest_first_then_recall(self):
        """L4: the whole sweep, its order, and the recall that still happens."""
        policy, _replayed, snapshot = self._replay_to_incident()
        transcript = []
        picked = []
        targets = []
        turn = snapshot.turn
        for _step in range(12):
            key = policy.choose_key(snapshot)
            transcript.append((policy.last_reason, key))
            if policy.last_reason == "return:seek-loot":
                remaining = self._routable(
                    policy, snapshot, sorted(policy._known_loot, key=lambda p: (p.y, p.x))
                )
                nearest = min(
                    snapshot.player.position.distance_to(position)
                    for position in remaining
                )
                targets.append(
                    (
                        policy._loot_target,
                        snapshot.player.position.distance_to(policy._loot_target),
                        nearest,
                    )
                )
            if policy.last_reason == "return:recall":
                break
            # Advance the recorded board by the bot's own action: a direction
            # key moves the player one cell, 'g' empties the grid it stands on.
            turn += 10
            position = snapshot.player.position
            if key[0] in MOVES:
                offset = MOVES[key[0]]
                target = Position(position.y + offset[0], position.x + offset[1])
                self.assertTrue(snapshot.grids[target].passable)
                snapshot = replace(
                    snapshot,
                    player=replace(snapshot.player, position=target),
                    turn=turn,
                )
            elif key[0] == "g":
                picked.append(position)
                grids = dict(snapshot.grids)
                grids[position] = replace(grids[position], object_count=0)
                snapshot = replace(snapshot, grids=grids, turn=turn)
            else:
                self.fail(f"unmodelled key {key!r} for reason {policy.last_reason!r}")

        self.assertEqual(
            transcript,
            [
                ("trigger-autodestroy", "7"),
                ("return:seek-loot", "6"),
                ("pickup", "g"),
                ("return:seek-loot", "6"),
                ("pickup", "g"),
                ("return:seek-loot", "1"),
                ("pickup", "g"),
                ("return:recall", "rg"),
            ],
        )
        self.assertEqual(picked, [BESIDE[0], BESIDE[1], UNDERFOOT])
        # Every routed pickup went to a nearest remaining item.
        for target, distance, nearest in targets:
            self.assertEqual((target, distance), (target, nearest))
        # The four items no route reaches are abandoned, and reading the scroll
        # is not cancelled by them.
        self.assertEqual(
            sorted(policy._known_loot, key=lambda p: (p.y, p.x)), list(UNREACHABLE)
        )
        self.assertEqual(self._routable(policy, snapshot, UNREACHABLE), [])

    def test_every_excluded_trigger_is_a_real_return_trigger(self):
        """A typo in the exclusion set would silently widen the sweep."""
        assigned = set()
        for module in ("policy", "policy_town", "policy_combat", "policy_quest"):
            source = (
                Path(__file__).parents[1] / "src" / "hengbot" / f"{module}.py"
            ).read_text(encoding="utf-8")
            assigned.update(
                match.group(1)
                for match in re.finditer(
                    r'_last_return_trigger\s*=\s*"([^"]+)"', source
                )
            )
            assigned.update(
                match.group(1)
                for match in re.finditer(r'"(\w[\w-]*)":\s*"(light-low)"', source)
            )
        self.assertTrue(
            RETURN_LOOT_SWEEP_CRITICAL_TRIGGERS <= assigned,
            RETURN_LOOT_SWEEP_CRITICAL_TRIGGERS - assigned,
        )

    def test_critical_resource_returns_keep_their_never_detour_rule(self):
        """The calm board does not clear hunger, darkness, pack or escape kit.

        These are the returns policy.py already declares critical, and
        tests/test_policy_identification.py's
        test_critical_return_does_not_detour_for_loot pins one of them.  A
        board with no hostile and a zero threat prediction says nothing about
        any of them, and the detour makes each one worse, so they are excluded
        from the loot-before-recall sweep.  Reported to the reviewer as the one
        place where the decision's "after the return trigger has fired" is not
        applied to every trigger.
        """
        for trigger in sorted(RETURN_LOOT_SWEEP_CRITICAL_TRIGGERS):
            with self.subTest(trigger=trigger):
                policy, _replayed, incident = self._replay_to_incident()
                policy._last_return_trigger = trigger

                key = policy.choose_key(incident)

                self.assertEqual(policy.last_reason, "return:recall")
                self.assertEqual(key, "rg")
                self.assertEqual(policy._loot_ledger_rearmed, set())

    def test_checkpoint_from_before_the_split_restores_and_decides(self):
        """A capture that predates the two new sets still replays."""
        policy, _replayed, incident = self._replay_to_incident()
        blocked = set(policy._nav_ledger_deferred_loot)
        self.assertTrue(blocked)
        del policy._nav_ledger_deferred_loot
        del policy._loot_ledger_rearmed

        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))

        self.assertEqual(restored._nav_ledger_deferred_loot, set())
        self.assertEqual(restored._loot_ledger_rearmed, set())
        key = restored.choose_key(incident)
        # Nothing is known to be ledger-deferred, so nothing is re-armed —
        # the old capture keeps its former deferrals — and the decision is
        # still the collection of the drop the player is standing on.
        self.assertEqual((restored.last_reason, key), ("trigger-autodestroy", "7"))
        self.assertEqual(restored._loot_ledger_rearmed, set())
        self.assertTrue(blocked <= set(restored._deferred_loot))

    def _recorded_ghoul(self):
        """A hostile actually recorded in this window, taken from its board."""
        board = next(
            record
            for record in self.inputs
            if record["decision"]["decision_sequence"] == 5384
        )["board"]
        snapshot = parse_snapshot(board, self.monrace)
        return next(
            monster for monster in snapshot.visible_monsters if monster.race_id == 128
        )


if __name__ == "__main__":
    unittest.main()
