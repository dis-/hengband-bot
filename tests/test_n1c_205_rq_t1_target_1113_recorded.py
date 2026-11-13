"""n1-c life-205, Angband 76F, RANDOM quest 42, 2026-11-13 01:31: the T1 target hunted.

Recorded: tests/fixtures/n1c-205-rq-t1-target-1113.json.xz
(tests/extract_n1c_205_rq_t1_target_1113_fixture.py): the boards of decisions 2450-2470.  The
quest's target 深淵の帝王『カントラス』 (race 830, Lv84, unique: a QUESTOR, which *Destruction*
only heals and teleports away, spells-floor.cpp:285-289) was shown by detection only, from 19
cells off at decision 2451; the Lv39 Magic-Eater walked toward it (``hunt:detected-target``,
decisions 2452 and 2464-2467) at T1 until one step took the HP from 365 to 67 (2468).

Owner 2026-11-13 (「ランダムクエストの討伐の標的が T1 と分かった時、どうしますか？」, answer
「階を諦めて帰還する」: 「T1 の標的と分かったら追わずに帰還を読み、クエストは失敗にする。標的が
近づく前に離れる。」).  Pinned here: A, the target judged from contact as the guardian is
(hunt_target ``_judge_quest_target``), a T1 not hunted; B, a target shown by
detection gives the floor up (the ``quest-unviable`` latch, which only a visible target fed);
C, a board where 即死 holds takes no hunt step; D, on a random quest floor whose exit lock holds,
*Destruction* still answers a sensed T1 that is not the target (owner 2026-11-05
「ランダムクエストの階であってもターゲットでなければ*破壊*してよい」).

Every decision is the public ``choose_key`` of a fresh fully loaded policy fed the recorded
boards in order (tests/support/recorded ``_policy``; its skill knowledge, ``skill``).
DECLARED CONSTRUCTED: no absorbed power list on the recorded replays (the live process had read
one; the recorded boards carry the detections it made); after the replay's own Word of Recall
read, the later boards carry ``recalling`` (the game would show it, the live process never read
one there); the constructed boards of B and D are named where they are built.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import hunt_target, threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy, skill
from tests.test_me_device_attacks import power_list, row

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-205-rq-t1-target-1113.json.xz"
KANTORAS = 830
QUEST = 42
FIRST_SHOWN = 2321070                                     # decision 2451, 19 cells off
HUNTED = (2321116, 2321120, 2321124, 2321132)             # decisions 2464-2467
LETHAL = 2321132                                          # decision 2467, next_action_p95 408 >= 365
BEGGAR = 10                                               # 醜い浮浪者 (Lv0), a beatable stand-in
TITAN = 1365                                              # a Lv63 non-target, T1 alone from contact
DESTRUCTION = row("*破壊*", 5, current=3, count=3)


class RqT1TargetRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.rows, cls.decisions = payload["rows"], payload["decisions"]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def row(self, turn):
        return copy.deepcopy(next(raw for raw in self.rows if raw["turn"] == turn))

    def policy(self, first, *powers):
        policy = _policy(self.root, self.races)
        policy.prime(parse_snapshot(copy.deepcopy(first), self.races))
        skill(policy, first)
        if powers:
            listed = dict(copy.deepcopy(first), turn=first["turn"] - 1,
                          _magic_eater_power_list=power_list("staff", *powers))
            observe_lists(policy, parse_snapshot(listed, self.races))
        return policy

    def decide(self, policy, raw):
        board = parse_snapshot(copy.deepcopy(raw), self.races)
        key = policy.choose_key(board)
        key = "" if key is None else str(key)
        if key:
            policy.confirm_key_posted(key)
        return board, key, policy.last_reason

    def replay(self):
        """{turn: (key, reason)} of one policy over every recorded board."""
        policy = self.policy(self.rows[0])
        decided, recalling = {}, False
        for raw in self.rows:
            raw = copy.deepcopy(raw)
            if recalling:
                raw["player"]["recalling"] = True  # DECLARED CONSTRUCTED (module docstring)
            _, key, reason = self.decide(policy, raw)
            decided[raw["turn"]] = (key, reason)
            recalling = recalling or reason == "return:recall"
        return policy, decided

    # ------------------------------------------------------------------ the recorded scene

    def test_the_recorded_scene(self):
        live = {row["sequence"]: (row["reason"], row["key"], row["hp"]) for row in self.decisions}
        self.assertEqual([live[sequence][0] for sequence in range(2464, 2468)],
                         ["hunt:detected-target"] * 4)
        self.assertEqual(live[2468], ("emergency:teleport", "rg", 67))
        self.assertEqual(live[2467][2], 365)
        for raw in self.rows:
            self.assertEqual((raw["floor"]["dungeon_id"], raw["floor"]["level"],
                              raw["floor"]["quest_id"]), (1, 76, QUEST))
        quest = next(q for q in self.row(FIRST_SHOWN)["progress"]["quests"] if q["id"] == QUEST)
        self.assertEqual(quest["r_idx"], KANTORAS)
        for turn in (FIRST_SHOWN, *HUNTED):
            raw = self.row(turn)
            self.assertIn(KANTORAS, [m["race_id"] for m in raw["detected_monsters"]])
            self.assertNotIn(KANTORAS, [m["race_id"] for m in raw["visible_monsters"]])

    # ------------------------------------------------------------------ A and B

    def test_the_t1_target_is_given_up_when_first_shown(self):
        """Live 2451: search, then the walk toward it; now Word of Recall on that board."""
        policy, decided = self.replay()
        self.assertEqual(decided[FIRST_SHOWN], ("rh", "return:recall"))
        board = parse_snapshot(self.row(FIRST_SHOWN), self.races)
        self.assertEqual(policy._unviable_quest_floor, board.floor_key)
        self.assertFalse([turn for turn, (_, reason) in decided.items()
                          if reason.startswith("hunt:")])

    def test_decisions_2464_to_2468_take_no_step_toward_it(self):
        """Live 2464-2467: hunt:detected-target toward it; now, recalling, it is left (「標的が
        近づく前に離れる」: inside its sensing radius the sensed T1 leave reads Teleportation)."""
        _, decided = self.replay()
        for turn in (*HUNTED, 2321139):
            self.assertFalse(decided[turn][1].startswith("hunt:"), (turn, decided[turn]))
        self.assertEqual({decided[turn] for turn in HUNTED if turn != LETHAL},
                         {("rg", "sensed-t1:teleport")})
        # 2467 holds 即死 (next_action_p95 408 >= HP 365, the target shown by detection only):
        # the shared ladder's 1-turn test reads the engagement on every board (n1-b life-391),
        # and owner 2026-11-09 B 「即死はテレポートで逃げる」 reads the same scroll first.
        self.assertEqual(decided[LETHAL], ("rg", "emergency:teleport"))

    def test_the_target_is_judged_from_contact_as_a_t1(self):
        policy = self.policy(self.rows[0])
        board, _, _ = self.decide(policy, self.row(FIRST_SHOWN))
        visit = hunt_target._visit(policy, board)
        self.assertTrue(visit.quest_unbeatable)
        self.assertIsNone(hunt_target.target_race(policy, board))

    def test_a_far_detected_t1_target_alone_gives_the_floor_up(self):
        """B, CONSTRUCTED: the first board shown to a fresh policy, カントラス moved 30 cells
        farther off (still detected only): the latch sees it, not only a visible target."""
        raw = self.row(FIRST_SHOWN)
        target = next(m for m in raw["detected_monsters"] if m["race_id"] == KANTORAS)
        target["x"] -= 30
        policy = self.policy(raw)
        board, key, reason = self.decide(policy, raw)
        self.assertEqual((key, reason), ("rh", "return:recall"))
        self.assertEqual(policy._unviable_quest_floor, board.floor_key)

    def test_a_beatable_detected_target_is_still_hunted(self):
        """CONSTRUCTED: the quest's target and the detected monster made a 醜い浮浪者 (Lv0)."""
        raw = self.row(FIRST_SHOWN)
        next(q for q in raw["progress"]["quests"] if q["id"] == QUEST)["r_idx"] = BEGGAR
        target = next(m for m in raw["detected_monsters"] if m["race_id"] == KANTORAS)
        target.update(race_id=BEGGAR, level=0)
        policy = self.policy(self.rows[0])
        self.decide(policy, self.row(self.rows[0]["turn"]))
        board, _, reason = self.decide(policy, raw)
        self.assertEqual(reason, "explore")  # live 2451 searched on the first sight as well
        raw["turn"] += 4  # CONSTRUCTED: the same board one decision later
        board, _, reason = self.decide(policy, raw)
        self.assertIsNone(policy._unviable_quest_floor)
        self.assertEqual(hunt_target.target_race(policy, board), BEGGAR)
        self.assertEqual(reason, "hunt:detected-target")

    # ------------------------------------------------------------------ C

    def test_no_hunt_step_where_instant_death_holds(self):
        """CONSTRUCTED: the target's verdict left out (``_judge_quest_target`` a no-op: as a
        T2/T3 target it is hunted), so the walk runs on the recorded boards; on decision 2467's
        board 即死 holds and the walk takes no step (live: '1' toward it, then 67 HP)."""
        with mock.patch.object(hunt_target, "_judge_quest_target", lambda *_: None):
            _, decided = self.replay()
            policy = self.policy(self.rows[0])
            for raw in self.rows:
                if raw["turn"] == LETHAL:
                    board = parse_snapshot(copy.deepcopy(raw), self.races)
                    break
                self.decide(policy, raw)
            self.assertTrue(threat_tiers.instant_death(policy, board).holds)
        self.assertEqual([decided[turn][1] for turn in HUNTED[:3]], ["hunt:detected-target"] * 3)
        self.assertNotEqual(decided[LETHAL][1], "hunt:detected-target")

    # ------------------------------------------------------------------ D

    def titan_board(self, dy, dx):
        """CONSTRUCTED: decision 2450's board (14,132; no target shown) with one awake タイタン
        detected at the offset, its only detected monster; the absorbed *破壊* staff row."""
        raw = self.row(self.rows[0]["turn"])
        raw["messages"] = []
        template = raw["detected_monsters"][0]
        raw["detected_monsters"] = [dict(template, index=900, race_id=TITAN, asleep=False,
                                         level=self.races[TITAN].level,
                                         y=raw["player"]["y"] + dy, x=raw["player"]["x"] + dx)]
        return raw

    def test_a_sensed_non_target_t1_in_reach_is_destroyed_on_the_locked_quest_floor(self):
        raw = self.titan_board(8, -4)
        policy = self.policy(raw, DESTRUCTION)
        board, key, reason = self.decide(policy, raw)
        self.assertTrue(policy._quest_floor_exit_locked(board))
        self.assertFalse(threat_tiers.leave_decided_here(policy, board))
        self.assertTrue(threat_tiers.destruction_only_here(policy, board))
        self.assertEqual(reason, "emergency:destruction:absorbed-power")
        self.assertTrue(key.startswith("mA"))

    def test_a_far_sensed_non_target_t1_is_gone_to_not_left(self):
        raw = self.titan_board(0, -18)  # 18 cells off: past the sure radius 13
        policy = self.policy(raw, DESTRUCTION)
        board, key, reason = self.decide(policy, raw)
        self.assertTrue(threat_tiers.inside_sensing(policy, board, board.detected_monsters[0]))
        self.assertEqual(reason, threat_tiers.APPROACH_REASON)

    def test_without_the_means_nothing_leaves_the_locked_quest_floor(self):
        """The use alone answers there: no stairs, scroll, Recall or walk away."""
        raw = self.titan_board(8, -4)
        policy = self.policy(raw)
        _, key, reason = self.decide(policy, raw)
        self.assertFalse(reason.startswith(threat_tiers.SENSED_LEAVE_PREFIX), (key, reason))
        self.assertNotEqual(reason, "return:recall")


if __name__ == "__main__":
    unittest.main()
