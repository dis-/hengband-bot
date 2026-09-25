"""A bot started while the game shows a store page composes its first board.

Recorded 2026-09-25 16:33: ``-Action resume`` attached to a game waiting on its
Home page.  The control server's ``state`` op carries no store payload and the
game writes a store row only when it draws the page or processes a key, so the
only store row was the one written before the reader attached at EOF.  The
process stopped at once with ``phase=store-state reason=missing or mismatching
current store page``.
"""

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _make_jsonl_barrier_drain
from hengbot.input_executor import OperationExecutor, ScreenKind, classify_screen


FIXTURES = Path(__file__).with_name("fixtures")
RECORDED_ROWS = FIXTURES / "resume-inside-home-store-20260925.jsonl.gz"
HOME_PAGE_LAYOUT = FIXTURES / "live-screens" / "28-after-menu-esc-20260915.json"


def recorded_rows() -> list[bytes]:
    with gzip.open(RECORDED_ROWS, "rb") as stream:
        return [line for line in stream.read().split(b"\n") if line.strip()]


def home_page_screen(store: dict) -> dict:
    """The recorded 211x67 Home page with the recorded row's letters/names."""
    screen = json.loads(HOME_PAGE_LAYOUT.read_text(encoding="utf-8"))["result"]
    lines = list(screen["lines"])
    for row, item in zip(range(6, 58), store["items"]):
        lines[row] = (" " * 65 + f"{item['letter']}) {item['name']}").ljust(211)[:211]
    screen["lines"] = lines
    return screen


class _Client:
    """Read-only control endpoint: one screen and one state reply."""

    observation_epoch = 0

    def __init__(self, screen, state):
        self.screen, self.state = screen, state
        self.requests: list[str] = []

    def request(self, op, **_fields):
        self.requests.append(op)
        return copy.deepcopy(self.screen if op == "screen" else self.state)


class ResumeInsideStorePins(unittest.TestCase):
    def setUp(self):
        self.surface_raw, self.store_raw = recorded_rows()
        self.surface = json.loads(self.surface_raw)
        self.store_row = json.loads(self.store_raw)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "bot-state-fixed.jsonl"

    def tcp_state(self, **overrides):
        # handle_state_request -> make_bot_json_snapshot: the same snapshot
        # with grid_map and message HISTORY, and never a store payload.
        state = copy.deepcopy(self.store_row)
        state.pop("store")
        state["type"] = "player_turn"
        state["grid_map"] = copy.deepcopy(self.surface["grid_map"])
        state.update(overrides)
        return state

    def attach(self, *rows: bytes):
        self.path.write_bytes(b"".join(row + b"\n" for row in rows))
        return _make_jsonl_barrier_drain(self.path)

    def test_recorded_rows_are_the_home_page_the_resume_attached_to(self):
        self.assertEqual((self.surface["type"], self.store_row["type"]),
                         ("player_turn", "store"))
        self.assertEqual(self.surface["turn"], self.store_row["turn"])
        store = self.store_row["store"]
        # page_size is the number of item slots on one page (letters a..Z on
        # a tall terminal), page_top the stock index of slot 'a'; the row
        # lists exactly that page.
        self.assertEqual((store["store_type"], store["page_top"],
                          store["page_size"], store["stock_num"]),
                         (7, 0, 52, 131))
        self.assertEqual(len(store["items"]),
                         min(store["page_size"], store["stock_num"] - store["page_top"]))
        self.assertEqual(classify_screen(home_page_screen(store)).kind, ScreenKind.STORE)

    def test_bootstrap_on_recorded_store_page_composes_the_store_board(self):
        drain = self.attach(self.surface_raw, self.store_raw)
        client = _Client(home_page_screen(self.store_row["store"]), self.tcp_state())
        executor = OperationExecutor(client, drain=drain)

        result = executor.observe_boundary(deadline=9999999999)

        self.assertEqual(result.outcome, "ready", result.reason)
        self.assertIs(result.screen.kind, ScreenKind.STORE)
        self.assertEqual(executor.ready_board["store"], self.store_row["store"])
        self.assertEqual(executor.ready_board["turn"], 5550750)
        # The attach row contributes the store payload only: no messages, and
        # it is not handed to the follow loop, which primes from it itself.
        self.assertEqual(executor.ready_board["messages"], [])
        self.assertEqual(drain.take_handed_records(), [])

    def test_attach_row_is_still_bound_to_the_tcp_state(self):
        for field, value in (("turn", 5550751),
                             ("inventory", self.store_row["inventory"][1:])):
            with self.subTest(field=field):
                drain = self.attach(self.surface_raw, self.store_raw)
                client = _Client(home_page_screen(self.store_row["store"]),
                                 self.tcp_state(**{field: value}))
                result = OperationExecutor(client, drain=drain).observe_boundary(
                    deadline=9999999999)
                self.assertEqual(result.outcome, "stuck-prompt")
                self.assertIn("phase=store-state", result.reason)

    def test_attach_row_is_still_bound_to_the_visible_page(self):
        drain = self.attach(self.surface_raw, self.store_raw)
        other = copy.deepcopy(self.store_row["store"])
        for item in other["items"]:
            item["name"] = "not-on-this-page-" + item["letter"]
        client = _Client(home_page_screen(other), self.tcp_state())
        result = OperationExecutor(client, drain=drain).observe_boundary(
            deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("phase=store-state", result.reason)

    def test_only_the_newest_board_before_attach_is_offered(self):
        # A surface board written after the store row proves that page closed.
        drain = self.attach(self.store_raw, self.surface_raw)
        self.assertIsNone(drain.store_record_at_attach())
        client = _Client(home_page_screen(self.store_row["store"]), self.tcp_state())
        result = OperationExecutor(client, drain=drain).observe_boundary(
            deadline=9999999999)
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_only_the_first_boundary_may_use_the_attach_row(self):
        drain = self.attach(self.surface_raw, self.store_raw)
        client = _Client(home_page_screen(self.store_row["store"]), self.tcp_state())
        executor = OperationExecutor(client, drain=drain)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        # No row was written since; a later barrier must not re-read the old one.
        again = executor.observe_boundary(deadline=9999999999)
        self.assertEqual(again.outcome, "stuck-prompt")
        self.assertIn("phase=store-state", again.reason)


if __name__ == "__main__":
    unittest.main()
