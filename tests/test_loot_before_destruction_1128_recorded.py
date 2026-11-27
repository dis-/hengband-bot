"""The hunt items before a non-urgent *Destruction* and before a Recall (supervisor 2026-11-28).

hunt_items (the one definition of a hunt item), destruction_loot (rules 1, 2 and 5: the hunt
piles in the circle fetched first, a hostile in view withholding the fetch only when the walk is
not survivable, a hunt pile no way reaches holding the use), full_pack_exchange and hunt_items
``walk_key`` (rules 3 and 4: the walk before and during a Recall no emergency reads, the full
pack's room by its cheapest spare, no plain sale-only gear while held at the speed ceiling).

Recorded (tests/extract_loot_before_destruction_1128_fixture.py), n1-b life-419 (Magic-Eater
CL50, permanent speed +17, on Angband's Ring of Speed hunt floors under the speed ceiling,
angband_cap ``ring_hunt_floor``):

* 2026-11-28 02:18:35, turn 13909797 at (18,73): the fetch toward the piles of the circle was
  walking ('destruction-loot:fetch-frontier') when a sleeping ドラウグル・ウォーカー came into view
  16 off; the fetch was withheld and the absorbed *Destruction* ('mA3') on the two sleeping
  sensed T1s deleted a Ring of Speed 13 off at (8,80) and 21 other items.
* 2026-11-27 22:14, turn 13066914 at (39,58): the fetch walked toward a Ring of Speed (27,60),
  『死神ももえ』 came into view 3 off after a hit of 163 (HP 959/1128), and the use ('mA3')
  deleted the ring 13 off.
* 2026-11-28 02:19, turn 13910555 at (15,51): the pack full (23/23), the Recall was read ('rk',
  ``pack-full``) with the Rings of Speed 15 off at (29,48), on a cell the area mapping did not
  hold, and 69 off at (16,120); the wait then picked up a 毛皮のクローク at (18,51).
* 2026-11-28 02:18:24, turn 13909659 at (34,77): a use on a sensed T1 with nothing known in the
  circle ('mA3', destruction_loot declined ``nothing-exposed``).

The boards are replayed as recorded through ``choose_key``, one decision a turn, each decision
completed as the executor would (``_completed_operation_owner`` the previous reason, as
tests/recorded_session_replay.py), from a board where the replay's decisions equal the live ones.

DECLARED CONSTRUCTED:
* the absorbed-power lists (``_me_device_lists``) are those of the same life's town-arrival
  checkpoint 20261128-050851 (the snapshot log does not carry them);
* ``replay`` with ``before=True``: the boards before the one asked are decided by the code
  before this change (no hunt pile, a hostile in view always withholds the fetch), so the
  policy's memory is the one live had on the board asked (with the change, the 02:17 prefix
  fetches on 13909746, where live cast, and the boards after it are no longer the ones live saw);
* ``test_c_..._identified_plain_cloak``: the cloak's name on the recorded 13910555 board is the
  one the game prints once it is identified (「毛皮のクローク [3,+5]」, the pack name of the live
  13910661 board).
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import angband_cap, destruction_loot, hunt_items, threat_tiers
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "loot-before-destruction-1128"
RING_0218 = Position(8, 80)
RING_2214 = Position(27, 60)
RING_PACK_FULL = Position(29, 48)
CLOAK = Position(18, 51)
DESTRUCTION_KEY = "mA3"


def _boards(name):
    lines = lzma.decompress((FIXTURE / name).read_bytes()).decode("utf-8")
    return [json.loads(line) for line in lines.splitlines() if line.strip()]


class LootBeforeDestruction1128RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.floors = {"0218": _boards("boards-0218.jsonl.xz"), "2214": _boards("boards-2214.jsonl.xz")}
        cls.lists = json.loads(lzma.decompress(
            (FIXTURE / "me-device-lists.json.xz").read_bytes()).decode("utf-8"))

    def replay(self, floor, first, asked, *, before=False):
        """Replay ``floor`` from ``first`` to the board before ``asked``: (policy, the asked raw
        board with the executor's completion, the (turn, reason, key) decided before)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        raws = [raw for raw in self.floors[floor] if raw["turn"] >= first]
        start = parse_snapshot(copy.deepcopy(raws[0]), self.monrace)
        policy.prime(start)
        policy._skill_exp_cache = (0, 0, start.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED (module docstring): the absorbed-power lists.
        policy._me_device_lists = {kind: (start.turn, tuple(rows))
                                   for kind, (_turn, rows) in self.lists.items()}
        decided, previous, seen = [], None, set()
        for raw in raws:
            if raw["turn"] in seen:
                continue
            seen.add(raw["turn"])
            raw = copy.deepcopy(raw)
            if previous is not None:
                raw["_completed_operation_sequence"] = len(seen)
                raw["_completed_operation_owner"] = previous
            if raw["turn"] == asked:
                return policy, raw, decided
            with contextlib.ExitStack() as stack:
                if before:
                    # DECLARED CONSTRUCTED (module docstring): the prefix decided as before.
                    stack.enter_context(mock.patch.object(
                        hunt_items, "hunt_piles", return_value=frozenset()))
                    stack.enter_context(mock.patch.object(
                        destruction_loot, "survivable", create=True, return_value=False))
                key = self.decide_board(policy, raw)
            decided.append((raw["turn"], policy.last_reason, key))
            previous = policy.last_reason if key else None
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError(f"board {asked} is not in the fixture")

    def decide_board(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        with contextlib.redirect_stdout(io.StringIO()):
            return policy.choose_key(board)

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return board, key, policy.last_reason

    def test_a_a_ring_of_speed_in_the_circle_is_fetched_before_the_destruction(self):
        policy, raw, decided = self.replay("0218", 13909700, 13909797, before=True)
        # The prefix is live's (decision log 13909702-13909792: 'destruction-loot:fetch-frontier').
        self.assertEqual(decided[-1][1:], ("destruction-loot:fetch-frontier", "9"))
        board, key, reason = self.decide(policy, raw)
        here = board.player.position
        self.assertEqual(here, Position(18, 73))
        self.assertTrue(angband_cap.ring_hunt_floor(policy, board))
        self.assertEqual(game_distance(here, RING_0218), 13)
        self.assertIn(RING_0218, hunt_items.hunt_piles(policy, board))
        self.assertIn(RING_0218, destruction_loot.exposed(policy, board))
        self.assertEqual([(m.name, m.asleep) for m in board.visible_monsters if m.hostile],
                         [("ドラウグル・ウォーカー", True)])
        self.assertFalse(threat_tiers.instant_death(policy, board).holds)

        # Recorded: ('mA3', 'emergency:destruction:absorbed-power'), deleting the ring.
        self.assertNotEqual(key, DESTRUCTION_KEY)
        self.assertIn(reason, (destruction_loot.FETCH_REASON, destruction_loot.FRONTIER_REASON))
        memory = getattr(policy, destruction_loot.MEMORY)
        goal = memory["frontier"] if reason == destruction_loot.FRONTIER_REASON else RING_0218
        self.assertLess(game_distance(goal, RING_0218), game_distance(here, RING_0218))

    def test_b_a_walk_the_prediction_does_not_survive_keeps_the_destruction(self):
        policy, raw, decided = self.replay("2214", 13066831, 13066914)
        self.assertEqual(decided[-1][1], "destruction-loot:fetch-frontier")
        board, key, reason = self.decide(policy, raw)
        self.assertIn(RING_2214, hunt_items.hunt_piles(policy, board))
        self.assertIn(RING_2214, destruction_loot.exposed(policy, board))
        awake = [m for m in (*board.visible_monsters, *board.detected_monsters)
                 if m.hostile and not m.asleep]
        self.assertIn("『死神ももえ』", [m.name for m in board.visible_monsters if not m.asleep])
        self.assertFalse(threat_tiers.instant_death(policy, board).holds)
        # The walk of 13 steps: the awake hostiles' prediction over it is past the HP (959).
        steps = game_distance(board.player.position, RING_2214)
        self.assertEqual(steps, 13)
        self.assertGreater(policy._predicted_damage(board, awake, turns=steps), board.player.hp)

        # Recorded: the use on the next board's flash (the ring deleted): as before.
        self.assertEqual((key, reason), (DESTRUCTION_KEY, "emergency:destruction:absorbed-power"))

    def test_c_the_pack_full_recall_walks_to_the_ring_of_speed_first(self):
        policy, raw, decided = self.replay("0218", 13910515, 13910555)
        board, key, reason = self.decide(policy, raw)
        self.assertEqual(len(board.inventory), 23)
        self.assertIsNone(board.grid_at(RING_PACK_FULL))

        # Recorded: ('rk', 'return:recall'): the Recall read, the ring left.
        self.assertEqual(policy._loot_target, RING_PACK_FULL)
        self.assertEqual(reason, hunt_items.SEEK_REASON)
        self.assertIn(key, tuple("12346789"))
        self.assertEqual(policy._last_return_trigger, "pack-full")
        self.assertTrue(hunt_items.speed_held(policy, board))
        self.assertIn(RING_PACK_FULL, hunt_items.hunt_piles(policy, board))

    def test_c_the_recall_wait_walks_to_the_ring_before_the_cloak(self):
        policy, raw, _decided = self.replay("0218", 13910515, 13910558)
        board, key, _reason = self.decide(policy, raw)
        self.assertTrue(board.player.recalling)
        self.assertLessEqual(game_distance(board.player.position, CLOAK), 3)

        # Recorded: ('1', 'seek-loot:exchange') toward the pile at (16,50), the cloak picked up
        # on 13910656.
        self.assertIn(key, tuple("12346789"))
        self.assertEqual(policy._loot_target, RING_PACK_FULL)

    def test_c_an_identified_plain_cloak_is_not_picked_up_at_the_ceiling(self):
        policy, raw, _decided = self.replay("0218", 13910515, 13910555)
        raw = copy.deepcopy(raw)
        names = raw["grid_map"]["found_item_names"]
        index = next(i for i, row in enumerate(names) if (row[0], row[1]) == (CLOAK.y, CLOAK.x))
        # DECLARED CONSTRUCTED (module docstring): the identified name.
        names[index] = [CLOAK.y, CLOAK.x, "毛皮のクローク [3,+5]"]
        board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
        grid = board.grid_at(CLOAK)
        self.assertTrue(hunt_items.sale_only_gear(policy, board, CLOAK))
        self.assertTrue(policy._floor_pile_is_junk(board, grid))
        # Unidentified as recorded it is still gone to and identified where it lies.
        recorded = policy.with_known_skill_exp(parse_snapshot(
            copy.deepcopy(self.replay("0218", 13910515, 13910555)[1]), self.monrace))
        self.assertFalse(hunt_items.sale_only_gear(policy, recorded, CLOAK))

    def test_e_a_kill_drop_is_a_remembered_pile_on_its_board(self):
        """Rule 5: the item ゼファーロード dropped at (19,51) on the recorded 13910280 board
        (「ゼファーロードを倒した。」) is a found item of that board, so the circle's piles
        (destruction_loot ``remembered_piles``) and the hunt piles read it like any other."""
        policy, raw, _decided = self.replay("0218", 13910270, 13910280)
        board = policy.with_known_skill_exp(parse_snapshot(raw, self.monrace))
        self.assertIn("ゼファーロードを倒した。", board.messages)
        self.assertIn(Position(19, 51), destruction_loot.remembered_piles(policy, board))

    def test_d_a_board_without_hunt_items_in_the_circle_decides_as_before(self):
        policy, raw, _decided = self.replay("0218", 13909600, 13909659)
        board, key, reason = self.decide(policy, raw)
        self.assertFalse(destruction_loot.exposed(policy, board))

        # Recorded: ('mA3', 'emergency:destruction:absorbed-power').
        self.assertEqual((key, reason), (DESTRUCTION_KEY, "emergency:destruction:absorbed-power"))


if __name__ == "__main__":
    unittest.main()
