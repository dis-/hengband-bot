"""Pins: the recall countdown is spent collecting, not standing still.

Live incident: Forest 24F, floor (7, 24, 0), 2026-09-23 20:10:13-20:10:19,
protocol 3, decisions 5384-5424 of one bot process.  An emergency teleport
('rf') relocated the player to (38, 55); the unique 悪鬼の血脈『ティボルト』
followed, was killed by the next melee ('8'), and dropped at (37, 55).  On the
board that followed, decision 5386 read Word of Recall ('rg') with hp 444/592,
zero visible hostiles, ``threat_prediction.total`` zero and SEVEN items on the
floor -- three of them at (38, 55) under the player, (37, 55) and (37, 56)
beside it.  Decisions 5387-5424 then posted WAIT ('5') on that same cell, 38
times, until the countdown fired and the floor was left with its loot on it.
The user's report: 「ユニークを倒してドロップ未回収で帰還」.

User decision 2026-09-23 (topic loot-before-recall), verbatim:
「見えている分は全部拾う」 -- if no hostile is visible and the threat
prediction is zero, the bot collects EVERY loot item it can see on the floor.
Follow-up question 「実装を『読んだ後の待ち時間に拾う』に統一しますか」,
answer 「待ち時間だけに統一（推奨）」: the collection belongs entirely to the
wait AFTER the scroll is read.  Reading is never delayed, so no return trigger
needs an exception; the countdown (``randint0(21) + 15`` game turns, see
``recall_player`` in src/spell-kind/spells-world.cpp) is what gets spent.  If
danger returns, the wait/survival behaviour wins immediately.  Loot not
collected when the recall fires is abandoned; the activation is never
cancelled.

Why the drop was left: the countdown rung of _return_to_town_key answered
``return:wait-recall`` WAIT unconditionally, and the ordinary loot owner sits
below the whole return owner in _decide (and is closed while
_emergency_return_active besides), so nothing could claim those 38 decisions.

``loot.blocker == "navigation-ledger:loot"`` is the NavigationLedger expiry: a
committed loot target whose best distance stopped improving for
NAV_TARGET_STALL_LIMIT decisions is deferred for the floor visit.  The flight
that preceded this board guarantees that plateau, so the fix hands those
positions one fresh budget when the calm countdown begins; each position is
released at most once per floor visit and expires again on its own if it still
cannot be approached.

The unique's drop is NOT distinguishable in the data: every one of the seven
entries is an ``object_count`` on a grid, with no owner, no kill and no
identity.  It is collected because it is visible floor loot, not because a
unique died on it.

Substrate: tests/fixtures/loot-before-recall-20260923.jsonl.gz, frozen by
tests/extract_loot_before_recall_fixture.py at decision boundaries taken from
``timing.jsonl_drain_records`` (see the .provenance.txt beside it).  It carries
decisions 5280-5387 with the board each one decided on, the 37 remaining
countdown decisions as RECORDS ONLY (their boards stop describing the replayed
run the moment the bot starts moving, so replaying them would be replay after
divergence), and the recorded ``~f`` skill list of the same character and run.

Replay fidelity: a restarted policy fed the frozen boards reproduces the
recorded REASON of all 108 decisions and the recorded (reason, key) of the last
eight up to and including the recall read; the earlier exploration keys differ
because a restart has no visit history.  Decision 5387 is the single divergence
in the window and is exactly the fix.

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
from hengbot.policy import HengbotPolicy


FIXTURE = (
    Path(__file__).parent / "fixtures" / "loot-before-recall-20260923.jsonl.gz"
)
FIXTURE_SHA256 = "f24e996e157887092490cc40acf19b690d4559f09c7570f19694a9b189b66aee"
MONRACES = Path(r"C:\hengband\lib\edit\MonraceDefinitions.jsonc")
RECALL = 5386  # the decision that read the scroll on top of the drop
COUNTDOWN = 5387  # the first decision of the countdown it started
UNDERFOOT = Position(38, 55)  # the item the player stood on
BESIDE = (Position(37, 55), Position(37, 56))  # the unique's drop and its neighbour
UNREACHABLE = (  # visible, but no route through the remembered map
    Position(25, 69),
    Position(26, 62),
    Position(26, 69),
    Position(27, 69),
)
# The returns policy.py calls critical, which under the previous draft of this
# fix needed an exception list.  Collecting only inside the countdown removes
# the need: reading is not delayed for any of them.
CRITICAL_TRIGGERS = (
    "pack-full",
    "food-hungry",
    "escape-kit-empty",
    "light-low",
    "no-light",
    "light-empty",
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
        cls.recorded_wait = [r["decision"] for r in records if r["role"] == "recorded-wait"]
        cls.monrace = load_monrace_knowledge(MONRACES)

    def _replay_to_recall(self):
        """Replay the frozen boards up to (not including) the countdown board."""
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
        countdown = self.inputs[-1]
        self.assertEqual(countdown["decision"]["decision_sequence"], COUNTDOWN)
        return policy, replayed, parse_snapshot(countdown["board"], self.monrace)

    def _routable(self, policy, snapshot, positions):
        return [
            position
            for position in positions
            if policy._position_target_step(snapshot, position) is not None
        ]

    def test_substrate_reproduces_the_recorded_run(self):
        """The frozen boards are the live decisions, not a re-derived story."""
        policy, replayed, countdown = self._replay_to_recall()
        self.assertEqual(len(replayed) + 1, 108)
        self.assertEqual(
            [record["reason"] for record, _reason, _key in replayed],
            [reason for _record, reason, _key in replayed],
        )
        self.assertEqual(
            [(reason, key) for _record, reason, key in replayed[-8:]],
            [
                (record["reason"], record["key"])
                for record, _reason, _key in replayed[-8:]
            ],
        )
        # The scroll was read on the recorded decision, with its recorded key.
        self.assertEqual(replayed[-1][0]["decision_sequence"], RECALL)
        self.assertEqual(replayed[-1][1:], ("return:recall", "rg"))
        # The live bot then spent every remaining countdown decision waiting.
        self.assertEqual(len(self.recorded_wait), 37)
        self.assertEqual(
            {(row["reason"], row["key"]) for row in self.recorded_wait},
            {("return:wait-recall", "5")},
        )
        self.assertEqual(
            {(row["position"]["y"], row["position"]["x"]) for row in self.recorded_wait},
            {(UNDERFOOT.y, UNDERFOOT.x)},
        )
        # The countdown board is the recorded one, and the loot is still on it.
        self.assertEqual(countdown.floor_key, (7, 24, 0))
        self.assertEqual(countdown.player.position, UNDERFOOT)
        self.assertTrue(countdown.player.recalling)
        self.assertEqual([m for m in countdown.visible_monsters if m.hostile], [])
        self.assertEqual([m for m in countdown.detected_monsters if m.hostile], [])
        state = policy.loot_state(countdown)
        self.assertEqual(len(state["visible"]), 7)
        self.assertEqual(
            {(item["position"]["y"], item["position"]["x"]) for item in state["visible"]},
            {(position.y, position.x) for position in (UNDERFOOT, *BESIDE, *UNREACHABLE)},
        )
        # The same quantity the decision log printed as threat_prediction.total.
        self.assertEqual(
            policy.threat_prediction(
                countdown,
                [m for m in countdown.visible_monsters if m.hostile],
            )["total"],
            0,
        )
        self.assertEqual(policy._last_return_trigger, "emergency-material-threat")

    def test_reading_the_scroll_is_never_delayed_by_any_trigger(self):
        """The recall read is untouched, so no trigger needs an exception.

        This is what replaced the trigger exclusion list of the first draft:
        tests/test_policy_identification.py's
        test_critical_return_does_not_detour_for_loot passes unchanged because
        nothing is inserted before the read at all.
        """
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
                match.group(1) for match in re.finditer(r'"(light-low)"', source)
            )
        self.assertTrue(set(CRITICAL_TRIGGERS) <= assigned, set(CRITICAL_TRIGGERS) - assigned)

        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy.consume_skill_knowledge(self.skill)
        for record in self.inputs[:-2]:
            policy.choose_key(parse_snapshot(record["board"], self.monrace))
        read_board = parse_snapshot(self.inputs[-2]["board"], self.monrace)
        self.assertEqual(self.inputs[-2]["decision"]["decision_sequence"], RECALL)
        for trigger in ("emergency-material-threat", *CRITICAL_TRIGGERS):
            with self.subTest(trigger=trigger):
                probe = restore_checkpoint(HengbotPolicy, checkpoint(policy))
                probe._last_return_trigger = trigger

                key = probe.choose_key(read_board)

                self.assertEqual((probe.last_reason, key), ("return:recall", "rg"))
                self.assertEqual(probe._loot_ledger_rearmed, set())

    def test_l1_the_countdown_collects_the_drop_instead_of_waiting(self):
        """L1: the first recorded wait decision becomes a collection."""
        policy, _replayed, countdown = self._replay_to_recall()
        # The ledger blocker was live on this board, exactly as recorded.
        self.assertEqual(policy._loot_defer_blocker, "navigation-ledger:loot")
        blocked = set(policy._nav_ledger_deferred_loot)
        self.assertTrue(blocked)
        self.assertTrue(blocked <= set(policy._deferred_loot))

        key = policy.choose_key(countdown)

        self.assertNotEqual((policy.last_reason, key), ("return:wait-recall", "5"))
        # The loot owner took the decision: the item underfoot is picked up
        # through the existing step-off that makes the game run its own floor
        # handling on re-entry (_current_floor_item_key, position unchanged).
        self.assertEqual((policy.last_reason, key), ("trigger-autodestroy", "7"))
        # The navigation-ledger deferral that would otherwise suppress the
        # collection was released, once, and the blocker cleared with it.
        self.assertEqual(policy._loot_ledger_rearmed, blocked)
        self.assertEqual(policy._nav_ledger_deferred_loot, set())
        self.assertFalse(blocked & policy._deferred_loot)
        self.assertIsNone(policy.loot_state(countdown)["blocker"])

    def test_l2_a_visible_hostile_waits_exactly_as_recorded(self):
        """L2: the gate closes on any visible hostile; the wait is unchanged."""
        policy, _replayed, countdown = self._replay_to_recall()
        # A hostile recorded on this run (古代の死霊, race 128) standing on a
        # known cell of this same board, far enough that no combat owner claims
        # the decision -- the only difference from L1 is that it is visible.
        board = replace(
            countdown,
            visible_monsters=[
                replace(
                    self._recorded_ghoul(),
                    position=Position(33, 62),
                    distance=7,
                    asleep=True,
                )
            ],
        )
        self.assertFalse(policy._loot_before_recall_calm(board))

        key = policy.choose_key(board)

        self.assertEqual((policy.last_reason, key), ("return:wait-recall", "5"))
        self.assertEqual(policy._loot_ledger_rearmed, set())

    def test_l3_a_nonzero_threat_prediction_waits_exactly_as_recorded(self):
        """L3: no visible hostile, but the prediction is not zero."""
        policy, _replayed, countdown = self._replay_to_recall()
        board = replace(
            countdown,
            detected_monsters=[
                replace(
                    self._recorded_ghoul(),
                    position=Position(36, 56),
                    distance=2,
                    asleep=True,
                )
            ],
        )
        self.assertEqual([m for m in board.visible_monsters if m.hostile], [])
        self.assertEqual(
            policy.threat_prediction(board, board.detected_monsters)["total"], 18
        )
        self.assertFalse(policy._loot_before_recall_calm(board))

        key = policy.choose_key(board)

        self.assertEqual((policy.last_reason, key), ("return:wait-recall", "5"))
        self.assertEqual(policy._loot_ledger_rearmed, set())

    def test_l4_every_reachable_item_is_collected_nearest_first_then_wait(self):
        """L4: the whole countdown sweep, its order, and the wait it returns to."""
        policy, _replayed, snapshot = self._replay_to_recall()
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
            if policy.last_reason == "return:wait-recall":
                break
            # Advance the recorded board by the bot's own action: a direction
            # key moves the player one cell, 'g' empties the grid it stands on.
            # The recorded boards of these decisions are deliberately NOT used:
            # from here on the live run and this one differ, and replaying past
            # a divergence proves nothing.
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
                ("return:wait-recall", "5"),
            ],
        )
        self.assertEqual(picked, [BESIDE[0], BESIDE[1], UNDERFOOT])
        # Every routed pickup went to a nearest remaining item.
        for target, distance, nearest in targets:
            self.assertEqual((target, distance), (target, nearest))
        # Seven decisions of the recorded 38-decision countdown were enough;
        # the four items no route reaches are abandoned and the wait resumes
        # without cancelling anything.
        self.assertLess(len(transcript), len(self.recorded_wait) + 1)
        self.assertTrue(snapshot.player.recalling)
        self.assertEqual(
            sorted(policy._known_loot, key=lambda p: (p.y, p.x)), list(UNREACHABLE)
        )
        self.assertEqual(self._routable(policy, snapshot, UNREACHABLE), [])

    def test_checkpoint_from_before_the_split_restores_and_decides(self):
        """A capture that predates the two new sets still replays."""
        policy, _replayed, countdown = self._replay_to_recall()
        blocked = set(policy._nav_ledger_deferred_loot)
        self.assertTrue(blocked)
        del policy._nav_ledger_deferred_loot
        del policy._loot_ledger_rearmed

        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))

        self.assertEqual(restored._nav_ledger_deferred_loot, set())
        self.assertEqual(restored._loot_ledger_rearmed, set())
        key = restored.choose_key(countdown)
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
