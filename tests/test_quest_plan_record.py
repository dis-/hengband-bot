"""The floor plans' state carried across a restart (quest_plan_record, owner 2026-11-23 K1 (b)-4), recorded.

Owner 2026-11-23 (verbatim): 「再起動でクエストの作戦の状態を「保存して続きから始める」（保存した階と今の
階が違えば捨てる）」.  Each case runs a recorded board sequence without a break (the uninterrupted
run), then again with a restart: a second policy that holds none of the first one's floor state
reads the record the first one's ``choose_key`` exit wrote and decides the next board through the
public ``choose_key``.  Its key and reason are the uninterrupted run's; a record of another floor
(or of a later game turn) is discarded, and the restart then decides as a fresh process did.

1. The 99F battle (n1-b life-411, tests/fixtures/n1b-finale-after-oberon-1121, as in
   tests/test_n1b_411_finale_after_oberon_1121_recorded): the battle's floor first seen with Oberon
   (quest 8) still TAKEN, his kill on this floor is the success recall (angband_finale_battle
   ``recall_permitted``).  A fresh process first sees the floor with quest 8 COMPLETED, reads it as
   done on arrival (``Battle.done_on_arrival``) and never reads the recall.  Compared here: the
   battle the restart restores (it is the uninterrupted one's) and the recall it permits, not the
   next key -- the uninterrupted run's next key is the map after its own *Destruction*
   (``me-power:after-destruction:map-area``), a memory of no floor plan.
2. The Q18 FIND_EXIT walk (n1-b life-414, tests/fixtures/n1b-414-q18-1122.jsonl.gz, as in
   tests/test_n1b_414_q18_shriek_ta_1122_recorded): the shrieks heard on the corridor make the choke
   (1,19) a fought one, held (the navigator's ``exit_fought_at``).  The restart between the last
   shriek and the choke restores the floor's navigator field by field and holds; a fresh process,
   which heard no shriek, walks on.

DECLARED CONSTRUCTED (case 1): as the module notes of test_n1b_411_finale_after_oberon_1121_recorded
(the expedition's mark, no return latched, no list re-read, the earlier 99F battle forgotten); the
arrival board 765 shown with quest 8 TAKEN (the floor first seen before the kill).  A restarted
process is the same town-arrival checkpoint loaded again (its floor memories are of the town); the
record is the file the first policy's exit wrote after board 765.
DECLARED RECONSTRUCTED (case 2): as test_n1b_414_q18_shriek_ta_1122_recorded (the absorbed power
lists of the same life's 08:48 checkpoint), read by the restarted process before its first decision
as the first one read them.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import pickle
import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import angband_finale, angband_finale_battle as battle, finale_prep, quest_plan_record
from hengbot.model import parse_snapshot
from support.town_arrival_fixture import load
from tests import test_n1b_414_q18_shriek_ta_1122_recorded as q18

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quest_plan_record_lint as lint  # noqa: E402

FINALE = Path(__file__).with_name("fixtures") / "n1b-finale-after-oberon-1121"
OBERON_QUEST = 8
TAKEN = 1


def _finale_boards():
    return {row["line"]: row["board"]
            for row in json.loads(lzma.decompress((FINALE / "boards.json.xz").read_bytes()))}


def _taken(raw):
    """DECLARED CONSTRUCTED: the board with Oberon's quest still TAKEN."""
    moved = copy.deepcopy(raw)
    for quest in moved["progress"]["quests"]:
        if quest["id"] == OBERON_QUEST:
            quest["status"] = TAKEN
    return moved


class FinaleRestartTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.raw = _finale_boards()

    def process(self, name, record=None):
        """A process: the town-arrival checkpoint loaded fresh, its record file beside it."""
        policy, _journal, _steps = load(FINALE, self.root / name / "fixture")
        self.addCleanup(policy._home_disposal.history_path.unlink, missing_ok=True)
        held = finale_prep.phase(policy)
        held.lifted, held.step, held.in_town = True, finale_prep.DONE, False  # DECLARED
        policy._returning_to_town, policy._last_return_trigger = False, None  # DECLARED
        policy._me_power_resume_reads = False  # DECLARED
        setattr(policy, battle.MEMORY, None)  # DECLARED (the earlier 99F's battle forgotten)
        path = self.root / name / quest_plan_record.FILE_NAME
        if record is not None:
            shutil.copyfile(record, path)
        policy._quest_plan_record_path = path
        return policy

    @staticmethod
    def decide(policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return key, policy.last_reason

    def uninterrupted(self):
        """The run without a break: the battle and the record its exit left after the arrival board,
        and the battle after the next."""
        policy = self.process("first")
        self.decide(policy, _taken(self.raw[765]))
        saved = self.root / "saved.pkl"
        shutil.copyfile(policy._quest_plan_record_path, saved)
        left = copy.deepcopy(getattr(policy, battle.MEMORY))
        self.decide(policy, self.raw[767])
        return policy, left, saved

    def test_the_uninterrupted_run_may_read_the_success_recall(self):
        policy, left, _saved = self.uninterrupted()
        self.assertFalse(left.done_on_arrival)
        self.assertTrue(battle.recall_permitted(policy, self.board(policy, 767)))

    def board(self, policy, line):
        return parse_snapshot(copy.deepcopy(self.raw[line]), policy._monrace_knowledge)

    def test_the_restart_resumes_the_battle(self):
        _policy, left, saved = self.uninterrupted()
        held = quest_plan_record.load(saved)
        self.assertEqual(held["floor"], (1, 99, 0))
        self.assertEqual(held["states"][battle.MEMORY], left)
        restarted = self.process("restarted", record=saved)
        restarted.prime(self.board(restarted, 767))
        self.assertEqual(getattr(restarted, battle.MEMORY), left)
        self.assertTrue(battle.recall_permitted(restarted, self.board(restarted, 767)))

    def test_a_fresh_process_may_not_read_the_recall(self):
        """The control: the restart without the record (as before the record)."""
        fresh = self.process("fresh")
        fresh.prime(self.board(fresh, 767))
        self.assertTrue(battle.battle(fresh, self.board(fresh, 767)).done_on_arrival)
        self.assertFalse(battle.recall_permitted(fresh, self.board(fresh, 767)))

    def discarded(self, name, **changes):
        _policy, _left, saved = self.uninterrupted()
        held = quest_plan_record.load(saved)
        held.update(changes)
        saved.write_bytes(pickle.dumps(held))
        restarted = self.process(name, record=saved)
        restarted.prime(self.board(restarted, 767))
        self.assertTrue(restarted._quest_plan_record_read)
        return restarted

    def test_a_record_of_another_floor_is_discarded(self):
        restarted = self.discarded("other-floor", floor=(1, 98, 0))
        self.assertFalse(battle.recall_permitted(restarted, self.board(restarted, 767)))

    def test_a_record_of_a_later_turn_is_discarded(self):
        """A game reloaded from an older save of the floor is not the floor the record saw."""
        restarted = self.discarded("older-save", turn=self.raw[767]["turn"] + 1)
        self.assertFalse(battle.recall_permitted(restarted, self.board(restarted, 767)))


def _q18_process(directory, first_turn, record=None):
    """A Q18 process (q18 ``drive``'s policy) primed on ``first_turn``, its record beside it."""
    Path(directory).mkdir(parents=True, exist_ok=True)
    policy = q18._policy(Path(directory), q18.MONRACE)
    path = Path(directory) / quest_plan_record.FILE_NAME
    if record is not None:
        shutil.copyfile(record, path)
    policy._quest_plan_record_path = path
    first = parse_snapshot(copy.deepcopy(q18.BOARDS[first_turn]), q18.MONRACE)
    policy.prime(first)
    policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
    for kind in ("staff", "wand", "rod"):
        listed = dict(copy.deepcopy(q18.BOARDS[first_turn]), turn=first_turn - 1,
                      _magic_eater_power_list={"kind": kind, "rows": q18._lists()[kind]})
        q18.observe_lists(policy, parse_snapshot(listed, q18.MONRACE))
    return policy


def _q18_decide(policy, turn, previous=None):
    raw = copy.deepcopy(q18.BOARDS[turn])
    if previous is not None:
        raw["_completed_operation_owner"] = previous
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, q18.MONRACE)))
    if key:
        policy.confirm_key_posted(key)
    return key, policy.last_reason


class Q18RestartTest(unittest.TestCase):
    """The FIND_EXIT walk of n1-b life-414 (tests/test_n1b_414_q18_shriek_ta_1122_recorded): after the
    shrieks on (1,16) and (2,18), the choke (1,19) holds as a fought one (quest_find_exit
    ``_shriek_hold``, the navigator's ``exit_fought_at``).  A restart between the last shriek and the
    choke holds it too; a fresh process, which heard no shriek, walks on (the recorded '3')."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        root = Path(cls.scratch.name)
        turns = [turn for turn in sorted(q18.BOARDS) if turn <= q18.ON_THE_CHOKE]
        cls.before = turns[-2]
        policy = _q18_process(root / "first", q18.START)
        previous = None
        for turn in turns:
            if turn == q18.ON_THE_CHOKE:
                cls.saved = root / "saved.pkl"
                shutil.copyfile(policy._quest_plan_record_path, cls.saved)
                cls.navigator = copy.deepcopy(policy._quest_navigators[18])
            key, reason = _q18_decide(policy, turn, previous)
            previous = reason if key else None
        cls.uninterrupted = (key, reason)
        cls.root = root

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_uninterrupted_run_holds_the_choke(self):
        self.assertEqual(self.uninterrupted, (q18.WAIT_KEY, q18.quest_find_exit.HOLD_REASON))

    def test_the_restart_resumes_the_walk_and_holds_alike(self):
        directory = self.root / "restarted"
        restarted = _q18_process(directory, q18.ON_THE_CHOKE, record=self.saved)
        navigator = restarted._quest_navigators[18]
        expected = {name: value for name, value in vars(self.navigator).items()
                    if name not in quest_plan_record.NAVIGATOR_NOT_CARRIED}
        self.assertEqual({name: vars(navigator).get(name) for name in expected}, expected)
        self.assertEqual(_q18_decide(restarted, q18.ON_THE_CHOKE), self.uninterrupted)

    def test_a_fresh_process_walks_on(self):
        """The control: the restart without the record (as before the record)."""
        directory = self.root / "fresh"
        fresh = _q18_process(directory, q18.ON_THE_CHOKE)
        self.assertEqual(_q18_decide(fresh, q18.ON_THE_CHOKE), ("3", q18.quest_find_exit.WALK_REASON))

    def test_a_record_of_another_floor_is_discarded(self):
        held = quest_plan_record.load(self.saved)
        self.assertEqual(held["floor"], (0, 35, 18))
        held["floor"] = (0, 36, 18)
        other = self.root / "other.pkl"
        other.write_bytes(pickle.dumps(held))
        directory = self.root / "other-floor"
        restarted = _q18_process(directory, q18.ON_THE_CHOKE, record=other)
        self.assertTrue(restarted._quest_plan_record_read)
        self.assertEqual(_q18_decide(restarted, q18.ON_THE_CHOKE), ("3", q18.quest_find_exit.WALK_REASON))


class LintTest(unittest.TestCase):
    """scripts/quest_plan_record_lint.py: every plan state carried or declared, no state off the policy."""

    def test_the_tree_has_no_finding(self):
        self.assertEqual(lint.findings(), [])

    def test_a_module_container_a_function_changes_is_found(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "quest_example.py"
            path.write_text("\n".join(("_SEEN = {}", "", "", "def note(x):", "    _SEEN[x] = 1",
                                       "    _SEEN.pop(x)", "")), encoding="utf-8")
            self.assertEqual(len(lint.module_state(path)), 2)

    def test_an_old_checkpoint_without_the_record_records_nothing(self):
        policy = ConservativePolicy(monrace_knowledge={})
        del policy.__dict__["_quest_plan_record_path"]
        board = parse_snapshot(copy.deepcopy(q18.BOARDS[q18.START]), q18.MONRACE)
        quest_plan_record.record(policy, board)
        self.assertFalse(quest_plan_record.restore(policy, board))


if __name__ == "__main__":
    unittest.main()
