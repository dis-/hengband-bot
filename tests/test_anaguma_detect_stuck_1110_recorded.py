"""Anaguma's casts go through their prompt owners (n1-c life-187/191, 2026-11-10).

The Anaguma pocket (anaguma, owner 2026-11-10 「50ゲームターン。待った後、可能なら感知を使って
状況を把握する。」) sent the absorbed Rod of Detection ``mCg`` under its bare reason
``anaguma:detect``.  No table of me_device_attacks_input owns that reason, so the key went out
raw: while the rod was ready the three keys happened to finish the command, but when it still
charged (the arrival's ``UCg``, or the previous detection) the game kept the power prompt
「('*'で一覧, ESCで中断) どの魔力を使いますか？」 and the bot stopped with
``stuck-prompt owner=anaguma:detect ... reason=unowned``: life-187 twice and life-191 twice,
and both lives were retired by it.  The pocket's absorbed Speed (``anaguma:close-haste``) had
the same bare reason, and its absorbed area attack replaced the device owner
(``ranged:magic-eater-device``) with ``ranged:anaguma-close-area``.

Recorded (tests/fixtures/anaguma-detect-stuck-20261110.json.gz, see
tests/extract_anaguma_detect_stuck_1110_fixture.py): n1-c life-191 (Magic-Eater), オークの
洞窟23階, every player-turn board from the first melt (turn 2722264) to the detection (turn
2722672), their decision rows, the absorption record and the game's screen at the stop.  The
boards are decided in order by one policy's public ``choose_key``; the plan is the policy's own.

DECLARED RECONSTRUCTED: the capture keeps no skill reply (as test_anaguma_recorded), and the
absorbed rod list the process remembered: the game displayed it when the arrival's ``UCg``
listed the rods (the Rod of Detection 0/1 charging, then cast), which the capture does not
keep as a board.  The utility decisions between the melts (``me-power:...``) are not posted,
so the replay's own differ (it does not see them done); the Anaguma rows are compared.
DECLARED CONSTRUCTED: the kind prompt screen (cmd-magiceat.cpp, as test_me_detection_rod_1101
builds it); the item and direction prompts of the carried devices (cmd-zaprod/cmd-usestaff/
cmd-aim, as test_destruction_use_1104 builds them); the carried Rod of Detection and Staff of
Detect Evil of the warrior-device cases; the absorbed Acid Ball row and the troll placed past
the mouth of the area case.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import anaguma, me_device_attacks
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import recorded as harness
from tests.support.recorded import EDIT, FaithfulHookGame, _policy, command_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

FIXTURE = Path(__file__).with_name("fixtures") / "anaguma-detect-stuck-20261110.json.gz"
DETECT_TURN = 2722672
FIRST_DIG_TURN = 2722264
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
DETECTION = "全感知"
AIM_PROMPT = "(持ち物:a-z, ESCで中断) どの魔法棒で狙いますか? "
ZAP_PROMPT = "(持ち物:a-z, ESCで中断) どのロッドを振りますか? "
USE_PROMPT = "(持ち物:a-z, ESCで中断) どの杖を使いますか? "
DIRECTION_PROMPT = "方向 ('*'でターゲット選択, ESCで中止)? "
ANAGUMA_REASONS = ("anaguma:", "melee:anaguma", "ranged:anaguma")
TVAL_ROD, TVAL_STAFF = 66, 55
SV_ROD_DETECTION, SV_STAFF_DETECT_EVIL = 6, 15
FOREST_TROLL = 297


def rod_row(name, charging, count=1, fail=10):
    return {"name": name, "charging": charging, "max": count, "fail": fail, "success": 100 - fail}


class AnagumaDetectStuckRecordedTest(harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    # ------------------------------------------------------------ the replay

    def replay(self, *, rods=(rod_row(DETECTION, 0),), until=DETECT_TURN, adjust=lambda raw: raw):
        """The policy after every recorded board up to ``until``: (policy, last raw, key)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        boards = [adjust(copy.deepcopy(raw)) for raw in self.data["boards"] if raw["turn"] <= until]
        first = parse_snapshot(copy.deepcopy(boards[0]), self.monrace)
        policy.prime(first)
        # DECLARED RECONSTRUCTED (module docstring): the skill reply and the remembered rod list.
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(self.data["absorbed"]))
        policy._me_device_lists = {"rod": (FIRST_DIG_TURN, tuple(rods))}
        decided = []
        for raw in boards:
            key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace)))
            decided.append((raw["turn"], policy.last_reason, key))
        return policy, boards[-1], decided

    def recorded(self):
        return {row["turn"]: (row["reason"], row["key"]) for row in self.data["decisions"]}

    def post(self, policy, raw, key, screens):
        """``key`` through the production decision send (cli._send_new_decision_key) and the
        executor; the game's accepted keys."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        game.screens = [*screens, command_screen(raw["turn"] + 10)]
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), self.monrace),
            posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
        return game.accepted

    def stop_screen(self):
        """The game's screen at the stop: the power prompt over the rod list, 全感知 1/1 charging."""
        screen = copy.deepcopy(self.data["stop_screen"])
        self.assertEqual(screen["input_context"]["kind"], "spell")
        self.assertIn("g) 全感知                 充填: 1/ 1", "\n".join(screen["lines"]))
        return screen

    # ------------------------------------------------------------ the pins

    def test_the_replay_reaches_the_recorded_detection_under_its_owner(self):
        _policy_, _raw, decided = self.replay()
        recorded = self.recorded()
        anaguma_rows = [(turn, reason, key) for turn, reason, key in decided
                        if recorded[turn][0].startswith(ANAGUMA_REASONS)]
        # Every recorded Anaguma decision is reproduced: the melts, steps, holds and blows.
        for turn, reason, key in anaguma_rows[:-1]:
            self.assertEqual((reason, key), recorded[turn], turn)
        self.assertEqual(recorded[DETECT_TURN], ("anaguma:detect", "mCg"))
        self.assertEqual(anaguma_rows[-1], (DETECT_TURN, "anaguma:detect" + CAST_SUFFIX, "mCg"))

    def test_the_charging_rod_closes_the_recorded_prompt(self):
        """The stop: the game's list shows the rod charging; the owner closes the prompt."""
        policy, raw, _ = self.replay()
        self.assertEqual(policy.last_reason, "anaguma:detect" + CAST_SUFFIX)
        accepted = self.post(policy, raw, "mCg", [prompt(TYPE_PROMPT), self.stop_screen()])
        self.assertEqual(accepted, ["m", "C", "\x1b"])

    def test_the_ready_rod_is_cast(self):
        policy, raw, _ = self.replay()
        accepted = self.post(policy, raw, "mCg", [prompt(TYPE_PROMPT),
                                                  power_screen("rod", [("g", DETECTION, 0, 1, 10)])])
        self.assertEqual(accepted, ["m", "C", "g"])

    def test_the_hold_detects_once(self):
        """After the closed prompt the hold waits again; no second detection on the next board."""
        policy, raw, _ = self.replay()
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10)
        key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(following, self.monrace)))
        self.assertNotEqual(policy.last_reason.split(":")[:2], ["anaguma", "detect"], key)

    def test_the_recorded_melt_with_the_carried_wand_is_accepted(self):
        """The warrior's path: the carried Stone to Mud wand, an item command and its direction."""
        policy, raw, decided = self.replay(until=FIRST_DIG_TURN)
        self.assertEqual(decided[-1], (FIRST_DIG_TURN, "anaguma:dig", "ah2"))
        accepted = self.post(policy, raw, "ah2", [
            harness.prompt_screen(AIM_PROMPT), harness.prompt_screen(DIRECTION_PROMPT)])
        self.assertEqual("".join(accepted), "ah2")

    def carried(self, raw, tval, sval, slot, name):
        """DECLARED CONSTRUCTED: a known, ready device in the pack."""
        item = dict(copy.deepcopy(raw["inventory"][0]), slot=slot, tval=tval, sval=sval, count=1,
                    known=True, aware=True, fully_known=True, charging=False, charges=5, pval=5,
                    name=name, weight=15, inscription="")
        if tval == TVAL_ROD:
            item["charging_count"] = 0
        raw["inventory"].append(item)
        return raw

    def test_a_carried_rod_of_detection_is_zapped_as_an_item(self):
        def adjust(raw):
            if raw["turn"] == DETECT_TURN:
                self.carried(raw, TVAL_ROD, SV_ROD_DETECTION, "w", "全感知のロッド")
            return raw
        policy, raw, decided = self.replay(adjust=adjust)
        turn, reason, key = decided[-1]
        self.assertEqual((reason, key[0]), ("anaguma:detect", "z"))
        accepted = self.post(policy, raw, key, [harness.prompt_screen(ZAP_PROMPT)])
        self.assertEqual(accepted, ["z", key[1:]])

    def test_a_carried_staff_of_detect_evil_serves_the_evil_pack(self):
        """No rod (the remembered list shows none): the troll pack is evil, the staff is used."""
        def adjust(raw):
            if raw["turn"] == DETECT_TURN:
                self.carried(raw, TVAL_STAFF, SV_STAFF_DETECT_EVIL, "w", "邪悪感知の杖 (5回分)")
            return raw
        policy, raw, decided = self.replay(rods=(), adjust=adjust)
        self.assertIn("EVIL", self.monrace[FOREST_TROLL].flags)
        turn, reason, key = decided[-1]
        self.assertEqual((reason, key[0]), ("anaguma:detect", "u"))
        accepted = self.post(policy, raw, key, [harness.prompt_screen(USE_PROMPT)])
        self.assertEqual(accepted, ["u", key[1:]])

    def test_the_absorbed_speed_is_cast_under_its_owner(self):
        """The close's haste (anaguma._haste_key): the absorbed Speed staff, 8 in the record."""
        policy, raw, _ = self.replay()
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        key = anaguma._haste_key(policy, board)
        self.assertEqual((policy.last_reason, key), ("anaguma:close-haste" + CAST_SUFFIX, "mAw"))
        accepted = self.post(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("staff", [("w", "スピード", 8, 8, 10)])])
        self.assertEqual(accepted, ["m", "A", "w"])
        # Spent: the owner closes the prompt.
        accepted = self.post(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("staff", [("w", "スピード", 0, 8, 10)])])
        self.assertEqual(accepted, ["m", "A", "\x1b"])

    def test_the_absorbed_area_attack_keeps_the_device_owner(self):
        """The close's area attack into the mouth (anaguma._area_into_mouth) with an absorbed ball."""
        ball = rod_row("アシッド・ボール", 0, fail=10)
        policy, raw, _ = self.replay(rods=(rod_row(DETECTION, 0), ball))
        plan = anaguma.plan(policy)
        here = Position(raw["player"]["y"], raw["player"]["x"])
        self.assertEqual(here, plan.pocket)
        # DECLARED CONSTRUCTED: the recorded troll two cells past the mouth on the pocket's line.
        dy, dx = plan.mouth.y - here.y, plan.mouth.x - here.x
        troll = copy.deepcopy(next(m for m in raw["detected_monsters"] if m["race_id"] == FOREST_TROLL))
        troll.update(y=here.y + 2 * dy, x=here.x + 2 * dx, asleep=False)
        raw = dict(copy.deepcopy(raw), visible_monsters=[troll])
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        key = anaguma._area_into_mouth(policy, board, plan, board.visible_monsters[0])
        self.assertIsNotNone(key)
        self.assertEqual(policy.last_reason, me_device_attacks.DEVICE_REASON)
        self.assertTrue(key.startswith("mC"), key)
        accepted = self.post(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("rod", [(key[2], "アシッド・ボール", 0, 1, 10)]),
            prompt(DIRECTION_PROMPT, "direction", can_choose_target=True)])
        self.assertEqual(accepted, ["m", "C", key[2], key[3]])
