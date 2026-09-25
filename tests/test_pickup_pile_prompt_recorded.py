"""Recorded pin: a pile pickup answers only floor choosers it observes.

Live incident 2026-09-26 01:57 (two minutes after a fresh start on the exe
built from upstream 36c570cc44 + bot JSON parity e55740cb22, protocol 3):
conquest looting on Orc cave 23F.  Decision 280 stepped onto (37,192); the
move's messages were "3 個のアイテムの山がある。" and "オーク・シャーマンの骨を
自動破壊します。", so the board decision 281 read (turn 5782217) already showed
the pile after the auto-destroy: 2 items (バトル・アックス, ヌンチャク), with
the pack at 22 of 23 slots.  ``_conquest_loot_key`` composed 'gaa' (one 'a'
per item seen) and the sender posted it as one atomic operation.

What the game did (the state log's next row, turn 5782222, is the
``player_turn`` written at the following command read): 'g' opened the floor
chooser (py_pickup_multiple_items counted 2 pickable items), the first 'a'
picked the battle axe -- the pack was now full -- and the second pass of the
loop found nothing that fits: "もうザックには床にあるどのアイテムも入らない。",
back to the command prompt with the ヌンチャク still on the floor.  The second
'a' was then read by the command loop as "aim a wand" and, the pack holding a
岩石溶解の魔法棒, opened "(持ち物:k-k,...) どの魔法棒で狙いますか?", which the
executor's classifier does not know: ``<stuck-prompt> owner=conquest:pickup
phase=continuation ... reason=unowned unknown: unrecognized``.

So the pile did not change between compose and post here (the JSON count was
right; protocol 3 plays no part): what changed was the number of choosers the
game would open, which the pack's free space bounds after each pick.  A
posted-ahead answer cannot know that.

Fix: the sender posts only 'g' and stages every 'a' as an optional answer to
an observed floor chooser (``_floor_pile_pickup_continuations``); an answer
whose chooser never comes is dropped at the command barrier, and a chooser
beyond the items seen is closed with ESC for the next decision to re-plan.
The classifier names the floor chooser from its source template.

Substrate: tests/fixtures/pickup-pile-prompt-20260926.jsonl.gz (written by
tests/extract_pickup_pile_prompt_fixture.py; provenance beside it).  Walls,
each declared:
- the conquest latch: ``_victory_loot_dungeon`` is policy memory from the
  guardian kill, before the capture; the recorded reason ``conquest:pickup``
  on dungeon 3 is produced only under that latch, so the replay sets it to 3;
- the skill list: the state log's last ``~f`` response (turn 5780207) is
  attached so the compose board is not spent on the periodic probe;
- the game: ``PilePickupGame`` below interprets the posted keys with the
  source rules quoted on it, seeded from the recorded compose board (pile,
  pack, wand); its command boundary after the pickup returns the recorded
  after board.  The pin first shows that this model, fed the pre-fix atomic
  'gaa', ends in the recorded stop with the recorded reason.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import copy
import gzip
import hashlib
import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from hengbot.cli import (
    PostingContract,
    SendResult,
    _ExecutorInputPort,
    _floor_pile_pickup_continuations,
    _send_new_decision_key,
)
from hengbot.control_client import ControlClient
from hengbot.input_executor import (
    FLOOR_PICKUP_PROMPT_PATTERN,
    OperationExecutor,
    ScreenKind,
    _cell_width,
    classify_screen,
)
from hengbot.model import TVAL_WAND, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import PACK_CAPACITY

from test_input_executor import FaithfulHookGame, command_screen, prompt_screen


FIXTURE = Path(__file__).parent / "fixtures" / "pickup-pile-prompt-20260926.jsonl.gz"
FIXTURE_SHA256 = "44d8d8d90b611ec21211cfb680c62225c2eadf1a23b751927b43475a4d15c56b"
EDIT = Path("C:/hengband/lib/edit")
STOP_KEY = "gaa"
STOP_REASON = "conquest:pickup"
PILE = (37, 192)
NO_ROOM_LEFT = "もうザックには床にあるどのアイテムも入らない。"
DEADLINE = 9999999999


def modal_screen(text):
    """A row-zero prompt over the map; prompts show the cursor after it."""
    value = prompt_screen(text)
    value["cursor"] = {"visible": True, "y": 0, "x": _cell_width(text)}
    return value


class PilePickupGame(FaithfulHookGame):
    """The posted keys interpreted by Hengband's pickup and command rules.

    - 'g' at the command prompt (carry -> py_pickup_floor,
      inventory/player-inventory.cpp:160-184): a lone item is picked without
      a chooser (py_pickup_single_item, :104-122); a pile counts its pickable
      items once and asks that many times (py_pickup_multiple_items,
      :124-151), each ask a floor chooser (floor-item-getter.cpp:428-461)
      listing only the items that still fit; when none fits the ask fails
      with "もうザックには床にあるどのアイテムも入らない。" and the loop ends.
    - 'a' in the chooser takes its first listed item; ESC ends the loop.
    - 'a' at the command prompt is "aim a wand" (input-key-processor.cpp:516,
      cmd-zapwand.cpp:336-338): with a wand in the pack it opens the
      inventory chooser "どの魔法棒で狙いますか? ".
    Items here never stack, so an item fits while the pack has a free slot.
    """

    def __init__(self, *, pile, free, wand_label, turn, after_states=()):
        super().__init__()
        self.pile = list(pile)
        self.free = free
        self.wand_label = wand_label
        self.mode = "command"
        self.picks_left = 0
        self.picked, self.messages = [], []
        self.after_states = list(after_states)
        self.state = {"turn": turn, "grid_map": {"runs": []}}
        self.screen = command_screen(turn)

    def _fits(self):
        return self.free > 0

    def _pick_first(self):
        self.picked.append(self.pile.pop(0))
        self.free -= 1
        self.messages.append(f"{self.picked[-1]}を拾った。")

    def _interpret(self, char):
        if self.mode == "command":
            if char == "g" and len(self.pile) == 1:
                if self._fits():
                    self._pick_first()
                else:
                    self.messages.append(f"ザックには{self.pile[0]}を入れる隙間がない。")
            elif char == "g" and len(self.pile) > 1:
                self.picks_left = len(self.pile) if self._fits() else 0
                if self.picks_left:
                    self.mode = "floor-chooser"
                else:
                    self.messages.append("ザックには床にあるどのアイテムも入らない。")
            elif char == "a" and self.wand_label is not None:
                self.mode = "aim-chooser"
            else:
                raise AssertionError(f"unmodelled command key {char!r}")
        elif self.mode == "floor-chooser":
            if char == "\x1b":
                self.mode = "command"
            elif char == "a":
                self._pick_first()
                self.picks_left -= 1
                if self.picks_left and not (self.pile and self._fits()):
                    self.messages.append(NO_ROOM_LEFT)
                    self.picks_left = 0
                if not self.picks_left:
                    self.mode = "command"
            else:
                raise AssertionError(f"unmodelled chooser key {char!r}")
        else:
            raise AssertionError(f"key {char!r} reached the {self.mode}")

    def _consume(self, *, pump_frontend=True):
        if pump_frontend and self.frontend_fifo:
            self.term_fifo.extend(self.frontend_fifo); self.frontend_fifo.clear()
        if not self.term_fifo:
            return
        raw = "".join(self.term_fifo); self.term_fifo.clear()
        for char in raw:
            self._interpret(char)
        if self.mode == "floor-chooser":
            last = chr(ord("a") + len(self.pile) - 1)
            self.screen = modal_screen(
                f"(床上:a-{last},'(',')', '*'一覧, ESC) どれを拾いますか？"
            )
        elif self.mode == "aim-chooser":
            label = self.wand_label
            self.screen = modal_screen(
                f"(持ち物:{label}-{label},'(',')', '*'一覧, ESC) どの魔法棒で狙いますか? "
            )
        else:
            # A player_turn row is written at the next command read.
            self.state = self.after_states.pop(0) if self.after_states else {
                "turn": self.state["turn"] + 5, "grid_map": {"runs": []},
                "messages": list(self.messages),
            }
            self.screen = command_screen(self.state["turn"])
            self.screen["lines"][0] = self.messages[-1] if self.messages else ""
            self.jsonl.append(dict(self.state))


def _records():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def _make(game):
    client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                           socket_factory=game.socket_factory)
    executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
    return client, executor


class PickupPilePromptRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        records = _records()
        cls.boards = {
            record["name"]: record["board"]
            for record in records if record["role"] == "board"
        }
        cls.decisions = {
            record["decision"]["decision_sequence"]: record["decision"]
            for record in records if record["role"] == "decision"
        }
        cls.stderr = next(r["stderr"] for r in records if r["role"] == "stop")
        cls.skill = next(
            r["board"] for r in records if r["role"] == "skill-knowledge"
        )
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    # ------------------------------------------------------------ helpers
    def _pile(self, name):
        entry = next(
            item for item in self.boards[name]["grid_map"]["found_item_names"]
            if tuple(item[:2]) == PILE
        )
        return entry[2:]

    def _game(self):
        compose = self.boards["compose"]
        wand = next(
            item["slot"] for item in compose["inventory"]
            if item["tval"] == TVAL_WAND
        )
        return PilePickupGame(
            pile=self._pile("compose"),
            free=PACK_CAPACITY - len(compose["inventory"]),
            wand_label=wand,
            turn=compose["turn"],
            after_states=[copy.deepcopy(self.boards["after"])],
        )

    def _ready(self, game):
        client, executor = _make(game)
        self.addCleanup(client.close)
        game.state = copy.deepcopy(self.boards["compose"])
        self.assertEqual(executor.observe_boundary(deadline=DEADLINE).outcome, "ready")
        return _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)

    def _decision(self):
        stop = self.decisions[281]
        return {"sequence": stop["decision_sequence"], "turn": stop["turn"],
                "reason": stop["reason"], "key": stop["key"]}

    # ------------------------------------------------------------ recorded
    def test_recorded_pickup_on_a_two_item_pile_with_one_free_slot(self):
        step, stop = self.decisions[280], self.decisions[281]
        self.assertEqual((step["key"], step["reason"]), ("2", "conquest:seek-loot"))
        self.assertEqual(
            (stop["decision_sequence"], stop["turn"], stop["key"], stop["reason"]),
            (281, 5782217, STOP_KEY, STOP_REASON),
        )
        # The auto-destroy was already applied to the board the key was
        # composed from: the 3-item pile message and the destroyed skeleton
        # left the 2 items the key has one 'a' for.
        self.assertEqual(
            stop["messages"],
            ["3 個のアイテムの山がある。", "オーク・シャーマンの骨を自動破壊します。"],
        )
        self.assertEqual(self._pile("compose"), ["バトル・アックス (2d8)", "ヌンチャク (2d3)"])
        self.assertEqual(stop["inventory"], {"used": 22, "free": 1})
        self.assertEqual(len(self.boards["compose"]["inventory"]), 22)
        # The next command read: one item picked, the pack full, the second
        # ask refused, the ヌンチャク still on the floor.
        after = self.boards["after"]
        self.assertEqual(after["turn"], 5782222)
        self.assertEqual(len(after["inventory"]), PACK_CAPACITY)
        self.assertEqual(
            after["messages"],
            ["バトル・アックス (2d8)(r)を拾った。", NO_ROOM_LEFT],
        )
        self.assertEqual(self._pile("after"), ["ヌンチャク (2d3)"])
        self.assertRegex(
            self.stderr,
            r"^<stuck-prompt> owner=conquest:pickup phase=continuation "
            r"transport=accepted request_id=\d+ "
            r"reason=unowned unknown: unrecognized$",
        )

    def test_p1_recorded_board_composes_the_recorded_key(self):
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy.prime(parse_snapshot(self.boards["previous"], self.monrace))
        policy.consume_skill_knowledge(self.skill)
        policy._victory_loot_dungeon = 3  # wall: the conquest latch
        compose = parse_snapshot(self.boards["compose"], self.monrace)
        key = policy.choose_key(compose)
        self.assertEqual((key, policy.last_reason), (STOP_KEY, STOP_REASON))
        self.assertIsNone(policy.peek_staged_prompt_chain())

    def test_model_reproduces_the_recorded_stop_for_the_atomic_macro(self):
        # The pre-fix sender: the whole composed key as one operation.
        game = self._game()
        port = self._ready(game)
        sent = port(STOP_KEY, decision=self._decision())
        self.assertIs(sent, SendResult.TERMINAL)
        self.assertEqual(game.accepted, [STOP_KEY])
        self.assertEqual(game.picked, ["バトル・アックス (2d8)"])
        self.assertEqual(game.pile, self._pile("after"))
        self.assertEqual(game.messages[-1], NO_ROOM_LEFT)
        self.assertEqual(game.mode, "aim-chooser")
        self.assertEqual(
            re.sub(r"request_id=\d+", "request_id=N", port.last_result.reason),
            re.sub(r"request_id=\d+", "request_id=N", self.stderr),
        )

    def test_p2_recorded_pickup_answers_only_the_observed_chooser(self):
        game = self._game()
        port = self._ready(game)
        compose = parse_snapshot(self.boards["compose"], self.monrace)
        sent, _line = _send_new_decision_key(
            port, "compose", STOP_KEY, None, set(), in_store=False,
            decision=self._decision(), snapshot=compose,
            posting_contract=PostingContract(),
        )
        self.assertIs(sent, SendResult.SENT)
        # 'g', then 'a' at the observed chooser; the second 'a' had no
        # chooser to answer and was never posted.
        self.assertEqual(game.accepted, ["g", "a"])
        self.assertEqual(game.mode, "command")
        self.assertEqual(game.picked, ["バトル・アックス (2d8)"])
        result = port.last_result
        self.assertEqual(result.outcome, "completed")
        self.assertIs(result.screen.kind, ScreenKind.COMMAND)
        self.assertEqual(result.operation.accepted_segments, ["g", "a"])
        board = result.board
        self.assertEqual(board["turn"], self.boards["after"]["turn"])
        self.assertEqual(board["messages"], self.boards["after"]["messages"])
        self.assertEqual(board["_completed_operation_owner"], STOP_REASON)
        self.assertEqual(
            [item["keys"] for item in
             board["_completed_operation_receipt"]["accepted_segments"]],
            ["g", "a"],
        )


def _snapshot(*, store=None):
    return SimpleNamespace(
        turn=1, floor_key=(3, 23, 0), messages=(), completed_operation_receipt=None,
        store=store, inventory=[], equipment=[],
        player=SimpleNamespace(position=Position(*PILE), gold=0, recalling=False),
    )


class PileChangedBetweenComposeAndPostTest(unittest.TestCase):
    """Whatever the pile is when 'g' runs, no answer is posted unobserved."""

    def _send(self, key, game):
        client, executor = _make(game)
        self.addCleanup(client.close)
        self.assertEqual(executor.observe_boundary(deadline=DEADLINE).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "compose", key, None, set(), in_store=False,
            decision={"sequence": 5, "reason": STOP_REASON},
            snapshot=_snapshot(), posting_contract=PostingContract(),
        )
        return sent, port.last_result

    def test_auto_destroy_shrank_the_pile_after_compose(self):
        # Composed for 3 items; one was destroyed before 'g' ran.
        game = PilePickupGame(pile=["剣", "盾"], free=5, wand_label="k", turn=10)
        sent, result = self._send("gaaa", game)
        self.assertIs(sent, SendResult.SENT)
        self.assertEqual(game.accepted, ["g", "a", "a"])
        self.assertEqual((game.picked, game.pile, game.mode), (["剣", "盾"], [], "command"))
        self.assertEqual(result.outcome, "completed")

    def test_pile_shrank_to_a_lone_item(self):
        # A lone item is picked by 'g' itself: no chooser, no answer.
        game = PilePickupGame(pile=["剣"], free=5, wand_label="k", turn=10)
        sent, result = self._send("gaa", game)
        self.assertIs(sent, SendResult.SENT)
        self.assertEqual(game.accepted, ["g"])
        self.assertEqual((game.picked, game.mode), (["剣"], "command"))

    def test_pile_grew_after_compose(self):
        # A chooser beyond the items seen is closed, not answered blind.
        game = PilePickupGame(pile=["剣", "盾", "兜"], free=5, wand_label="k", turn=10)
        sent, result = self._send("gaa", game)
        self.assertIs(sent, SendResult.SENT)
        self.assertEqual(game.accepted, ["g", "a", "a", "\x1b"])
        self.assertEqual((game.picked, game.pile, game.mode),
                         (["剣", "盾"], ["兜"], "command"))
        self.assertEqual(result.outcome, "completed")

    def test_pack_filled_before_the_pile_drained(self):
        game = PilePickupGame(pile=["剣", "盾", "兜"], free=2, wand_label="k", turn=10)
        sent, result = self._send("gaaa", game)
        self.assertIs(sent, SendResult.SENT)
        self.assertEqual(game.accepted, ["g", "a", "a"])
        self.assertEqual((game.picked, game.pile), (["剣", "盾"], ["兜"]))
        self.assertEqual(game.messages[-1], NO_ROOM_LEFT)

    def test_an_unknown_screen_after_g_still_stops(self):
        game = PilePickupGame(pile=["剣", "盾"], free=5, wand_label="k", turn=10)
        original = game._consume

        def unknown_after_g(**kwargs):
            original(**kwargs)
            if game.mode == "floor-chooser":
                game.screen = modal_screen("An unknown prompt")

        game._consume = unknown_after_g
        sent, result = self._send("gaa", game)
        self.assertIs(sent, SendResult.TERMINAL)
        self.assertEqual(game.accepted, ["g"])
        self.assertIn("reason=unowned unknown: unrecognized", result.reason)

    def test_home_get_command_is_not_staged(self):
        store = SimpleNamespace(store_type=7)
        self.assertIsNone(_floor_pile_pickup_continuations(_snapshot(store=store), "gaa"))
        self.assertIsNone(_floor_pile_pickup_continuations(None, "gaa"))
        self.assertIsNone(_floor_pile_pickup_continuations(_snapshot(), "g"))
        self.assertIsNone(_floor_pile_pickup_continuations(_snapshot(), "ga"))
        prefix, continuations = _floor_pile_pickup_continuations(_snapshot(), "gaa")
        self.assertEqual(prefix, "g")
        self.assertEqual([item.keys for item in continuations], ["a", "a", "\x1b"])
        self.assertTrue(all(item.optional for item in continuations))


class FloorChooserClassificationTest(unittest.TestCase):
    def test_floor_chooser_is_owned_in_both_languages(self):
        for row0 in (
            "(床上:a-b,'(',')', '*'一覧, ESC) どれを拾いますか？",
            "(床上:a-c,'(',')', Enter 次, ESC) どれを拾いますか？",
            "(Floor: a-b,'(',')', * to see, ESC) Get which item? ",
        ):
            match = classify_screen(modal_screen(row0))
            self.assertEqual((match.kind, match.feature),
                             (ScreenKind.ITEM_SOURCE, row0.rstrip()))
            self.assertIsNotNone(re.fullmatch(FLOOR_PICKUP_PROMPT_PATTERN, match.feature))

    def test_other_get_prompts_are_not_the_floor_chooser(self):
        home = classify_screen(modal_screen("(Items a-x, ESC to exit) Get which item?"))
        self.assertIsNone(re.fullmatch(FLOOR_PICKUP_PROMPT_PATTERN, home.feature))
        aim = classify_screen(modal_screen(
            "(持ち物:k-k,'(',')', '*'一覧, ESC) どの魔法棒で狙いますか? "))
        self.assertEqual((aim.kind, aim.feature), (ScreenKind.UNKNOWN, "unrecognized"))


if __name__ == "__main__":
    unittest.main()
