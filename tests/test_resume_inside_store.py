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
from hengbot.input_executor import (
    OperationExecutor, ScreenKind, _cell_width, classify_screen, compose_barrier_board,
)


FIXTURES = Path(__file__).with_name("fixtures")
RECORDED_ROWS = FIXTURES / "resume-inside-home-store-20260925.jsonl.gz"
HOME_PAGE_LAYOUT = FIXTURES / "live-screens" / "28-after-menu-esc-20260915.json"
RECORDED_SCREEN_ROWS = FIXTURES / "home-page-20260915-screen28-row.jsonl.gz"


def recorded_rows() -> list[bytes]:
    with gzip.open(RECORDED_ROWS, "rb") as stream:
        return [line for line in stream.read().split(b"\n") if line.strip()]


def _fit(text: str, cells: int) -> str:
    """Cut ``text`` to ``cells`` terminal cells and pad it to exactly that."""
    out, used = "", 0
    for char in text:
        width = _cell_width(char)
        if used + width > cells:
            break
        out, used = out + char, used + width
    return out + " " * (cells - used)


def home_page_screen(store: dict, *, names=None, page_number=None) -> dict:
    """Draw a Home page the way view/display-store.cpp does, inside the
    recorded 211x67 Home screen (fixture 28) whose menu rows are kept.

    Slot k: label at row k + 6, symbol at column 3, name from column 5 cut
    where the weight is written at column 67; "-続く-" below the last slot and
    the page indicator at row 5, column 20 while the stock spans pages.
    """
    screen = json.loads(HOME_PAGE_LAYOUT.read_text(encoding="utf-8"))["result"]
    lines = list(screen["lines"])
    origin = (screen["width"] - 80) // 2
    names = names if names is not None else [item["name"] for item in store["items"]]
    multiple = store["stock_num"] > store["page_size"]
    number = page_number or store["page_top"] // store["page_size"] + 1

    def draw(y: int, logical: str) -> None:
        lines[y] = " " * origin + _fit(logical, 80) + " " * (screen["width"] - origin - 80)

    draw(5, _fit("    アイテムの一覧", 20)
         + _fit(f"({number}ページ)  " if multiple else "", 50) + "  重さ")
    for y in range(6, 6 + store["page_size"] + 1):
        draw(y, "")
    for position, name in enumerate(names):
        label = chr(ord("a") + position) if position < 26 else chr(ord("A") + position - 26)
        draw(position + 6, _fit(f"{label}) ! {name}", 67) + "  0.5 kg")
    if multiple:
        draw(6 + len(names), "   -続く-")
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
        self.path = Path(directory.name) / "attach-state.jsonl"

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

    def bootstrap(self, screen, store_raw=None):
        drain = self.attach(self.surface_raw, store_raw or self.store_raw)
        client = _Client(screen, self.tcp_state())
        return OperationExecutor(client, drain=drain).observe_boundary(
            deadline=9999999999)

    def test_same_turn_other_page_sharing_one_name_does_not_bind(self):
        # At the same turn the screen shows page 2 of the Home, and one name
        # of page 1 (slot G, '鑑定の杖 (8x 16回分)') is also drawn there.  A
        # name-anywhere check would bind page 1's letters and stock to page 2.
        store = self.store_row["store"]
        shared = store["items"][32]["name"]
        page_two = [f"二頁目の品物{position}" for position in range(len(store["items"]))]
        page_two[3] = shared
        screen = home_page_screen(store, names=page_two, page_number=2)
        self.assertIn(shared, "\n".join(screen["lines"]))
        result = self.bootstrap(screen)
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("phase=store-state", result.reason)

    def test_page_indicator_must_agree_with_page_top(self):
        result = self.bootstrap(home_page_screen(self.store_row["store"], page_number=2))
        self.assertEqual(result.outcome, "stuck-prompt")
        self.assertIn("phase=store-state", result.reason)

    def test_every_slot_must_carry_its_own_item(self):
        store = self.store_row["store"]
        names = [item["name"] for item in store["items"]]
        cases = {
            "shifted-one-slot": names[1:] + ["次の品物"],
            "two-slots-swapped": [names[1], names[0]] + names[2:],
        }
        for case, shown in cases.items():
            with self.subTest(case=case):
                result = self.bootstrap(home_page_screen(store, names=shown))
                self.assertEqual(result.outcome, "stuck-prompt")
                self.assertIn("phase=store-state", result.reason)

    def test_a_partial_last_page_must_end_where_the_row_ends(self):
        # Derived: the recorded row cut to a 40-item single page.
        row = copy.deepcopy(self.store_row)
        row["store"]["items"] = row["store"]["items"][:40]
        row["store"]["stock_num"] = 40
        raw = json.dumps(row, ensure_ascii=False).encode("utf-8")
        names = [item["name"] for item in row["store"]["items"]]
        self.assertEqual(
            self.bootstrap(home_page_screen(row["store"]), raw).outcome, "ready")
        for case, screen in {
            "extra-slot-below": home_page_screen(
                row["store"], names=names + [self.store_row["store"]["items"][40]["name"]]),
            "page-indicator-on-single-page": home_page_screen(
                dict(row["store"], stock_num=53), names=names),
        }.items():
            with self.subTest(case=case):
                result = self.bootstrap(screen, raw)
                self.assertEqual(result.outcome, "stuck-prompt")
                self.assertIn("phase=store-state", result.reason)

    def test_a_name_cut_at_the_weight_column_still_binds(self):
        row = copy.deepcopy(self.store_row)
        long_name = "アニマルスレイヤーのカットラス (1d7) (+8,+6) (+3) {+知;活/X動~耐魅}"
        row["store"]["items"][1]["name"] = long_name
        raw = json.dumps(row, ensure_ascii=False).encode("utf-8")
        screen = home_page_screen(row["store"])
        self.assertNotIn(long_name, screen["lines"][7])
        self.assertIn(long_name[:20], screen["lines"][7])
        result = self.bootstrap(screen, raw)
        self.assertEqual(result.outcome, "ready", result.reason)
        self.assertEqual(result.board["store"], row["store"])
        # A name cut short of the weight column is not the game's truncation.
        names = [item["name"] for item in row["store"]["items"]]
        names[1] = long_name[:10]
        result = self.bootstrap(home_page_screen(row["store"], names=names), raw)
        self.assertEqual(result.outcome, "stuck-prompt")

    def test_recorded_screen_binds_only_the_row_of_its_own_page(self):
        # Recorded 2026-09-15: screen 28 and the Home rows the game wrote for
        # page 1 (shown; names cut at the weight column in slots R and T) and
        # page 2 of the same 62-item stock.
        with gzip.open(RECORDED_SCREEN_ROWS, "rb") as stream:
            page_two, page_one = [
                json.loads(line) for line in stream.read().split(b"\n") if line.strip()]
        screen = json.loads(HOME_PAGE_LAYOUT.read_text(encoding="utf-8"))["result"]
        self.assertEqual((page_one["store"]["page_top"], page_two["store"]["page_top"]),
                         (0, 52))
        for row, expected in ((page_one, True), (page_two, False)):
            state = {key: value for key, value in row.items() if key != "store"}
            with self.subTest(page_top=row["store"]["page_top"]):
                board, _ = compose_barrier_board(
                    state, screen, ScreenKind.STORE, [], attach_store_record=row)
                self.assertEqual(board is not None, expected)

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
