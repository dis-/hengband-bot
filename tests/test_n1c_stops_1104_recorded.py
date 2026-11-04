"""The n1-c stops of 2026-11-04 on the viewing bots (stops-1104-0750 and stops-1104-1330).

Recorded: tests/extract_n1c_stops_1104_fixtures.py.  Town stops replay from
their arrival checkpoints through the public chooser; the dungeon stops decide
on their recorded boards.  Facts the capture keeps outside the board are marked
DECLARED CONSTRUCTED.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_powers, me_staff_sequence
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import Position
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
from test_hourly_0700_1102_recorded import RecordedTownPolicy
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures") / "n1c-stops-1104"


def _boards():
    with gzip.open(FIXTURES / "boards.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


class TownStops(executor_pins.ProductionHarness):
    def setUp(self):
        super().setUp()
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, stop):
        visit = self.scratch / stop / "town-arrival"
        visit.mkdir(parents=True)
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((FIXTURES / stop / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((FIXTURES / stop / "journal.jsonl.xz").read_bytes())))
        runtime = self.scratch / stop / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        Path(policy._home_disposal.history_path).unlink(missing_ok=True)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def assert_posts(self, policy, row, board, key):
        """The production executor posts ``key`` on the recorded board."""
        raw_board = json.loads(row["line"] or row["inputs"][-1])
        game = executor_pins.FaithfulHookGame()
        game.state = raw_board
        game.screen = executor_pins.command_screen(raw_board["turn"])
        # DECLARED CONSTRUCTED: the next board after the command.
        game.screens = [executor_pins.command_screen(raw_board["turn"] + 10)]
        game.states = [dict(raw_board, turn=raw_board["turn"] + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            posting_contract=PostingContract(),
        )
        self.assertTrue(sent)

    def test_a_town_fight_is_not_the_opening_routes_standstill(self):
        """life-127 07:31:30: six shots and a rest on one cell killing a mercenary,
        then no-progress:quest on the walk to Q1's entrance."""
        policy, recorded, steps = self.load("opening-fight")
        result = replay_window("opening-fight", policy, iter(steps[:-1]))
        self.assertIsNone(result.first_divergence)
        board = steps[-1][1]()
        key = policy.choose_key(board)
        # Recorded: ('', 'quest:blocked:opening-route').
        self.assertIsNone(getattr(policy, "_opening_q1_failure", None))
        self.assertEqual((key, policy.last_reason), ("9", "quest:enter:approach"))
        self.assert_posts(policy, recorded[-1], board, key)

    def test_the_staff_sequence_waits_for_a_pending_inscription(self):
        """life-127 07:36:26: the Magic Shop page leaves for the worn light's
        random-teleport inscription; the sequence stepped off and back in
        (7, 3, ESC) until no-progress:buy.

        The checkpoint replays only with the recorded keys acknowledged, the
        calibration file being the live process's.  DECLARED CONSTRUCTED: the
        optimizer's selection of the worn light (the live blocker
        pending-random-teleport-suppression).
        """
        policy, recorded, steps = self.load("staff-inscription")
        for entry, supply in steps[:13]:
            policy.choose_key(supply())
            if entry["key"]:
                policy.confirm_key_posted(entry["key"])
        light = next(owned.id for owned in policy._equipment_catalog.items
                     if owned.origin == "equipped" and owned.equipped_slot == "light")
        policy._equipment_preparation_selected_ids = lambda _preparation: frozenset({light})
        key = policy.choose_key(steps[13][1]())
        self.assertEqual((key, policy.last_reason), ("\x1b", "shop:observe-and-leave"))
        policy.confirm_key_posted(key)
        key = policy.choose_key(steps[14][1]())
        # Recorded: ('7', 'shop:approach').
        self.assertEqual((key, policy.last_reason), ("wja", "town:restore-combat-weapon"))
        policy.confirm_key_posted(key)
        board = steps[15][1]()
        key = policy.choose_key(board)
        # Recorded: ('3', 'shop:approach').
        self.assertEqual((key, policy.last_reason),
                         ("{/g.\r", "equipment:suppress-equipped-random-teleport"))
        self.assert_posts(policy, recorded[15], board, key)

    def test_hunger_keeps_the_trip_to_the_tower_that_recharges_the_staple(self):
        """life-128 13:05:31 (Lv36, retired): both Wands of Wonder empty, 38170 gold
        against a 3344 gold expedition, walking to the inn.  Turning hungry on the
        way sent the mana override to Home (a Wand of Speed Monster and one of
        Disarming it may not eat) and the Magic shop, then the named stop.

        「減ったら塔でチャージする」."""
        policy, recorded, steps = self.load("tower-hunger")
        result = replay_window("tower-hunger", policy, iter(steps[:18]))
        self.assertIsNone(result.first_divergence)
        board = steps[18][1]()
        self.assertEqual(board.player.food_state, "hungry")
        key = policy.choose_key(board)
        # Recorded: ('`n(.', 'survival:mana-home-travel').
        self.assertEqual((key, policy.last_reason), ("3mc", "me-staff:travel-morivant"))
        self.assert_posts(policy, recorded[18], board, key)

    def test_a_fourth_staff_of_a_kind_is_absorbed(self):
        """life-128 12:18:16: after the Tower's recharge, a fourth Staff of Speed
        stopped as absorb-no-progress:staff:22 although the earlier three went in:
        the attempt count never restarted on a success.

        DECLARED CONSTRUCTED: the checkpoint's count already holds those three, so
        the previous absorption's settling is declared on the first board.  Not
        posted: the executor answers ``G`` at the game's item prompt, which no
        recorded screen shows; this key's path is the one the earlier three took.
        """
        policy, _recorded, steps = self.load("fourth-absorb")
        record = me_staff_sequence.state(policy)
        self.assertEqual(record.attempts[("absorb", "staff:22")], 3)
        record.pending = ("absorb", (("staff:22", record.absorbed["staff:22"]),))
        for entry, supply in steps[:-1]:
            policy.choose_key(supply())
            if entry["key"]:
                policy.confirm_key_posted(entry["key"])
        board = steps[-1][1]()
        key = policy.choose_key(board)
        # Recorded: ('', 'quest:blocked:me-staff').
        self.assertEqual(policy.last_reason, me_staff_sequence.ABSORB_REASON)
        self.assertTrue(key.startswith("G"), key)
        self.assertIsNone(record.failure)


class DungeonStops(RecordedTownPolicy):
    @classmethod
    def setUpClass(cls):
        cls.case = _boards()

    def test_no_absorbed_power_is_asked_for_while_berserk(self):
        """life-125 06:47:49: 「激怒の発作」 gave berserk; ``mAi`` was refused at
        command input (「狂戦士化していて頭が回らない！」) and the bot stopped."""
        case = self.case["berserk"]
        # DECLARED CONSTRUCTED: an empty Home list; the sequence's absorption
        # record is read from the stop's checkpoint.
        policy = self.primed(case["stop"], [], case["skill"])
        me_staff_sequence.state(policy).absorbed.update(case["absorbed"])
        board = self.board(policy, case["stop"])
        self.assertIn("berserk", board.player.status_bar)
        key = policy.choose_key(board)
        # Recorded: ('mAi', 'me-power:dark-room:lite-area').
        self.assertFalse(key.startswith("m"), key)
        self.assertFalse(policy.last_reason.startswith("me-power:"), policy.last_reason)

    def test_a_kept_away_monster_is_not_walked_back_to_past_another_hostile(self):
        """life-125 07:18:17: the walk to shoot reached (3,65), a sleeping ゾンビ・イーク
        came into view and the board went to seek-loot, whose step out of view
        started the walk again."""
        case = self.case["loop"]
        boards = case["boards"]
        # DECLARED CONSTRUCTED: an empty Home list.
        policy = self.primed(boards[0], [], case["skill"])
        for raw, expected in zip(boards, (("7", "seek-loot"),
                                          ("3", "immobile-threat:approach-to-shoot"),
                                          ("7", "seek-loot"))):
            key = policy.choose_key(self.board(policy, raw))
            self.assertEqual((key, policy.last_reason), expected)
            policy.confirm_key_posted(key)
        key = policy.choose_key(self.board(policy, boards[3]))
        # Recorded: ('3', 'immobile-threat:approach-to-shoot').
        self.assertNotEqual(policy.last_reason, "immobile-threat:approach-to-shoot")
        self.assertNotEqual(key, "3")

    def test_a_monster_in_the_corridor_does_not_end_exploration_only_while_in_view(self):
        """life-128 08:23:51 (Dungeon 18F): from (3,2) the frontiers lie along the
        corridor east, so explore steps to (2,3); there two 日光猿 19 squares along
        come into view, their cells leave the floor index, no frontier is reachable
        and the ladder steps back toward the stairs, out of view.  40 decisions.

        DECLARED CONSTRUCTED: the remembered map is read from the stop's policy
        state and the floor's two map-area casts from its decision log, with an
        empty Home list.
        """
        with gzip.open(FIXTURES / "blocked-corridor.json.gz", "rt", encoding="utf-8") as stream:
            case = json.load(stream)
        policy = self.primed(case["stop"], [], case["skill"])
        cells = lambda name: {tuple(cell) for cell in case["terrain"][name]}
        policy._remembered_floor_t |= cells("floor_t")
        policy._remembered_known_t |= cells("known_t")
        policy._remembered_marked_t |= cells("marked_t")
        policy._remembered_wall_t |= cells("wall_t")
        policy._probed_frontiers |= {Position(*cell) for cell in case["probed"]}
        policy._engagement_avoid_cells |= {Position(*cell) for cell in case["avoid"]}
        for visit in case["visit_counts"]:
            policy._visit_counts[Position(*visit["key"])] = visit["count"]
        board = self.board(policy, case["stop"])
        mapping = ("staff", me_powers.SV_STAFF_MAPPING)
        setattr(policy, me_powers.MEMORY, me_powers.FloorMemory(board.floor_key, board.turn - 1, uses=[
            me_powers.Use(mapping, mapping, "new-floor", Position(*cast), turn)
            for cast, turn in (((14, 43), 614980), ((6, 10), 615343))]))
        key = policy.choose_key(board)
        # Recorded: ('1', 'stuck:seek-stairs'); here, with no stairs remembered,
        # the same ladder answers ('4', 'stuck:wander').
        self.assertEqual((key, policy.last_reason), ("6", "explore"))


if __name__ == "__main__":
    unittest.main()
