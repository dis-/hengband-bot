"""n1-a life-528 2026-11-16 07:47: the Treasure Detection buy refused for a slot the 啓蒙の薬 held.

The Lv40 warrior (device skill 33, *Destruction* staff 1.6% at 50F, no staff at Home or in
the pack, no telepathy) arrived from a Yeek cave 1F fundraising run.  Castle 51 lacks
*Destruction* and telepathy, the fallback floor is 31 (deepest 51 - 20, owner 2026-11-13) and
no entered landing lies in 31-48, so the no-safe-destination fundraising set opened
(owner 2026-11-10).  It took its two diggers from Home (pack 19 of 23); the Alchemist shelved
45 Treasure Detection at 23 gold (57,944 gold), but the purchase kept the four-slot reserve
(``_next_purchase`` full-pack-nonstacking) and the pack tidy found nothing to shelve
(``room_can_be_made`` False): the 啓蒙の薬 carried since an earlier visit was held as Q25's
optional carry.  The plan ran out (fundraise:fallback-exhausted-plan), the recall gate named
town:blocked:depth-gate:destination-51 until loop-detected.  8b2800b77 did not change it (the
same replay on its parent stops the same way).

Owner 2026-11-16 (verbatim): 「必須携行品だけで枠が不足することはない。荷物整理処理に不具合がある」.
The potion is no requirement (owner 2026-11-05: it blocks no departure) and a fundraising set
requests no quest, so during the set its retention holds only while it is carried into its
quest (filed this visit, on foot to the Home, or the quest taken); otherwise it is ordinary
Home stock and the tidy shelves it on the set's first Home page (row 23).

Recorded: the town-arrival checkpoint, its 49 journal rows and the sidecar files
(tests/extract_n1a_528_depth_gate_1116_fixture.py).

DECLARED CONSTRUCTED:
* ``before_the_stop``: rows 0-42 replayed with the old retention (the window always open), the
  recorded path, to ask the tidy on row 43's own board.
* the row-43 board without the 啓蒙の薬 (as the fixed visit's Home deposit leaves it).
* the taken-Q25 board and the closed set of the retention test.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import destruction_use, fallback_depth_floor, quest_optional_carry, town_pack_headroom
from hengbot.model import QuestState
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import PACK_CAPACITY, QUEST_STATUS_TAKEN
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-528-depth-gate-1116"
ENLIGHTENMENT = "啓蒙の薬"
DETECTION = "財宝感知の巻物"
OBSERVED_ROW = 43
STOP_ROW = 48
SET_ROW = 21  # fundraising:no-safe-destination opens the set
DEPOSIT_ROW = 23
STOP_REASON = "town:blocked:depth-gate:destination-51:missing-destruction,telepathy"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1a528DepthGateRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policies = []
        # The fixed code on the recorded boards up to its first own decision.
        cls.policy, cls.journal, cls.steps = cls.load("real")
        cls.replayed = []
        for recorded, supply in cls.steps[:DEPOSIT_ROW + 1]:
            board = supply()
            key = cls.policy.choose_key(board)
            cls.replayed.append(((key, cls.policy.last_reason), (recorded["key"], recorded["reason"])))
            post(cls.policy, key)
        # DECLARED CONSTRUCTED: the recorded path to row 43 under the old retention.
        cls.before, _journal, steps = cls.load("before")
        cls.before_replayed = []
        with mock.patch.object(quest_optional_carry, "_carried_for_quest",
                               lambda *_args: True, create=True):
            for recorded, supply in steps[:OBSERVED_ROW]:
                key = cls.before.choose_key(supply())
                cls.before_replayed.append(((key, cls.before.last_reason),
                                            (recorded["key"], recorded["reason"])))
                post(cls.before, key)
        cls.observed = steps[OBSERVED_ROW][1]()

    @classmethod
    def load(cls, name):
        loaded = load(FIXTURE, Path(cls.scratch.name) / name)
        cls.policies.append(loaded[0])
        return loaded

    @classmethod
    def tearDownClass(cls):
        for policy in cls.policies:
            policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_a_the_recorded_stop(self):
        self.assertEqual(self.journal[STOP_ROW]["reason"], STOP_REASON)
        self.assertEqual(self.journal[OBSERVED_ROW]["reason"],
                         "town-progress-invariant:continue-observed-shop")
        board = self.steps[0][1]()
        player = board.player
        self.assertEqual((player.class_id, player.level, player.device_skill), (0, 40, 33))
        self.assertLess(destruction_use.staff_success(player, 50), 2)
        self.assertFalse(any(self.policy._is_destruction_staff(item)
                             for item in (*board.inventory, *self.policy._home_knowledge_items)))
        self.assertEqual(self.policy._missing_required_abilities(board, 51),
                         {"destruction", "telepathy"})
        self.assertEqual(self.policy._missing_required_abilities(board, 49), set())
        self.assertEqual((fallback_depth_floor.deepest_reached(self.policy, board),
                          fallback_depth_floor.floor(self.policy, board)), (51, 31))
        self.assertIsNone(self.policy._pick_alternate_dungeon(
            board, max_entry_depth=48, prefer_deepest=True, refused_dungeon=12))

    def test_b_the_recorded_path_to_the_alchemist(self):
        for row, (decided, recorded) in enumerate(self.before_replayed):
            self.assertEqual(decided, recorded, row)
        board = self.observed
        self.assertEqual(board.store.store_type, 4)
        self.assertEqual(len(board.inventory), 19)
        shelf = next(item for item in board.store.items if item.name == DETECTION)
        self.assertEqual((shelf.count, shelf.price), (45, 23))
        self.assertEqual(self.before._count_treasure_detection_scrolls(board), 0)
        self.assertEqual(self.before._fundraising_mode, "prepare")

    def test_c_the_tidy_shelves_the_optional_carry(self):
        policy, board = self.before, self.observed
        potion = next(item for item in board.inventory if item.name == ENLIGHTENMENT)
        self.assertEqual(quest_optional_carry.retained(policy, board, potion), 0)
        self.assertEqual(policy._retention_reservation(board, potion), 0)
        self.assertTrue(town_pack_headroom.room_can_be_made(policy, board))
        self.assertEqual([item.name for item in board.inventory
                          if town_pack_headroom.preservable(policy, board, item)], [ENLIGHTENMENT])
        self.assertEqual(policy._find_home_deposit(board).name, ENLIGHTENMENT)

    def test_d_the_set_s_first_home_page_deposits_it(self):
        for row, (decided, recorded) in enumerate(self.replayed[:DEPOSIT_ROW]):
            self.assertEqual(decided, recorded, row)
        self.assertTrue(self.journal[SET_ROW]["reason"].startswith(
            "town:entrance-step-off:fundraising:no-safe-destination:"))
        # Row 23: the set's first Home page shelves the potion (slot f) instead of the
        # recorded catalogue-shortage exit before the two diggers' take.
        self.assertEqual(self.journal[DEPOSIT_ROW]["reason"], "home:queue-catalogue-shortage")
        self.assertEqual(self.replayed[DEPOSIT_ROW][0], ("df", "home:atomic-deposit"))
        board = self.steps[DEPOSIT_ROW][1]()
        self.assertEqual(next(item for item in board.inventory if item.slot == "f").name,
                         ENLIGHTENMENT)

    def test_e_without_it_the_alchemist_sells_the_detection(self):
        # DECLARED CONSTRUCTED: row 43's page without the deposited potion.
        policy, board = self.before, self.observed
        board = replace(board, inventory=tuple(item for item in board.inventory
                                               if item.name != ENLIGHTENMENT))
        self.assertLess(len(board.inventory), PACK_CAPACITY - 4)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("pp10\r\r", "shop:in-store-buy"))
        self.assertEqual(next(item for item in board.store.items if item.letter == "p").name,
                         DETECTION)

    def test_f_outside_the_set_or_taken_it_stays_carried(self):
        # DECLARED CONSTRUCTED: Q25 taken; the set closed.
        policy, board = self.before, self.observed
        potion = next(item for item in board.inventory if item.name == ENLIGHTENMENT)
        self.assertFalse(quest_optional_carry._carried_for_quest(policy, board, potion))
        self.assertNotIn(25, board.quests)  # an untaken quest is absent from the board
        taken = replace(board, quests={**board.quests,
                                       25: QuestState(id=25, status=QUEST_STATUS_TAKEN)})
        self.assertTrue(quest_optional_carry._carried_for_quest(policy, taken, potion))
        with mock.patch.object(policy, "_fundraising_mode", None):
            self.assertTrue(quest_optional_carry._carried_for_quest(policy, board, potion))
            self.assertEqual(quest_optional_carry.retained(policy, board, potion), 1)

if __name__ == "__main__":
    unittest.main()
