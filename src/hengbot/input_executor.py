"""Serialized input execution at Hengband's blocking Term-read boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping, Sequence
import unicodedata
import re

from hengbot.control_client import KeyPostOutcome, KeyPostStatus, raw_keys_to_macro_notation


class ScreenKind(str, Enum):
    COMMAND = "command"
    STORE = "store"
    BUILDING = "building"
    ITEM_SOURCE = "item-source"
    ITEM_TARGET = "item-target"
    DIRECTION = "direction"
    MORE = "more"
    CONFIRM = "confirm"
    QUANTITY = "quantity"
    KNOWLEDGE = "knowledge"
    LOOK = "look"
    FILE_VIEWER = "file-viewer"
    IDENTIFY_VIEWER_PAGE = "identify-viewer-page"
    IDENTIFY_VIEWER_FINAL = "identify-viewer-final"
    CHARACTER = "character"
    DEATH = "death"
    UNKNOWN = "unknown"


class ExecutorState(str, Enum):
    READY = "ready"
    AWAITING_KEYS_ACK = "awaiting-keys-ack"
    AWAITING_WM_FENCE = "awaiting-wm-fence"
    AWAITING_SCREEN = "awaiting-screen"
    AWAITING_STATE = "awaiting-state"
    CONTINUATION = "continuation"
    TERMINAL = "terminal"


class Transport(str, Enum):
    TCP = "tcp"
    WM = "wm"


@dataclass(frozen=True)
class ScreenMatch:
    kind: ScreenKind
    feature: str
    row: int | None = None
    column: int | None = None


def _cell_width(text: str) -> int:
    """Match bot-screen.cpp:67-73: wide/full-width UTF-8 glyphs use 2 cells."""
    return sum(2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1 for ch in text)


def _suffix_match(row: str, suffixes: Sequence[str]) -> tuple[str, int] | None:
    for suffix in suffixes:
        if row.endswith(suffix):
            return suffix, _cell_width(row[:-len(suffix)])
    return None


def classify_screen(screen: Mapping[str, object]) -> ScreenMatch:
    """Pure, conservative classifier for source-derived main-term templates."""
    raw = screen.get("lines")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ScreenMatch(ScreenKind.UNKNOWN, "missing-lines")
    lines = [str(line).rstrip() for line in raw]
    if not lines:
        return ScreenMatch(ScreenKind.UNKNOWN, "empty-screen")
    row0 = lines[0]

    # player/player-damage.cpp:471,503; core/game-closer.cpp:53.
    terminal = ("You die.", "You are broken.", "Stand by for later score registration?",
                "後でスコアを登録するために待機しますか？")
    for y, line in enumerate(lines):
        for literal in terminal:
            if literal in line:
                return ScreenMatch(ScreenKind.DEATH, literal, y, _cell_width(line[:line.index(literal)]))

    # view/display-messages.cpp:185-207 (row zero only).
    found = _suffix_match(row0, ("-more-", "-続く-"))
    if found:
        return ScreenMatch(ScreenKind.MORE, found[0], 0, found[1])
    # core/asking-player.cpp:225-255.
    found = _suffix_match(row0, ("[Y/n]", "[y/n]", "[(O)k/(C)ancel]"))
    if found:
        return ScreenMatch(ScreenKind.CONFIRM, row0, 0, found[1])
    # core/asking-player.cpp:343-351. The editable default follows the colon.
    if re.search(r"(?:Quantity \(1-|いくつですか \(1-)\d+\):(?: .*)?$", row0):
        return ScreenMatch(ScreenKind.QUANTITY, row0, 0, 0)
    # target/target-getter.cpp:56-61,118-120.
    direction_prompts = ("Direction (Escape to cancel)?", "方向 (ESCで中断)?",
        "Direction ('5' for target, '*' to re-target, Escape to cancel)?",
        "Direction ('*' to choose a target, Escape to cancel)?",
        "方向 ('5'でターゲットへ, '*'でターゲット再選択, ESCで中断)?",
        "方向 ('*'でターゲット選択, ESCで中断)?")
    if row0 in direction_prompts:
        return ScreenMatch(ScreenKind.DIRECTION, row0, 0, 0)
    # inventory/floor-item-getter.cpp:460-461; spells-perception.cpp:125;
    # store/store.cpp:185. Require the exact prompt suffix, not history text.
    source_prompts = ("Read which scroll?", "Use which staff?", "Zap which rod?",
                      "どの巻物を読みますか?", "どの杖を使いますか?", "どのロッドを振りますか?")
    if any(row0.endswith(prompt) for prompt in source_prompts):
        return ScreenMatch(ScreenKind.ITEM_SOURCE, row0, 0, 0)
    if row0.endswith(("Identify which item?", "どのアイテムを鑑定しますか?")):
        return ScreenMatch(ScreenKind.ITEM_TARGET, row0, 0, 0)
    if row0.startswith("(Items ") and "ESC to exit)" in row0:
        return ScreenMatch(ScreenKind.ITEM_SOURCE, row0, 0, 0)

    # perception/identification.cpp:762-799. These markers are at cell x=15.
    attr_rows = [(y, line) for y, line in enumerate(lines)
                 if line.startswith(" " * 15 + "Item Attributes:") or
                 line.startswith(" " * 15 + "アイテムの能力:")]
    if attr_rows:
        for y, line in enumerate(lines):
            if line.startswith(" " * 15 + "-- more --") or line.startswith(" " * 15 + "-- 続く --"):
                return ScreenMatch(ScreenKind.IDENTIFY_VIEWER_PAGE, line.strip(), y, 15)
            if line.startswith(" " * 15 + "[Press any key to continue]") or line.startswith(" " * 15 + "[何かキーを押すとゲームに戻ります]"):
                return ScreenMatch(ScreenKind.IDENTIFY_VIEWER_FINAL, line.strip(), y, 15)
        return ScreenMatch(ScreenKind.UNKNOWN, "incomplete-identify-viewer")

    # cmd-io/cmd-knowledge.cpp:32-69: fixed logical rows, including row-17 more.
    if len(lines) > 21 and lines[3] in ("Display current knowledge", "現在の知識を確認する") \
            and lines[20].startswith(("Command:", "コマンド:")) \
            and lines[21].startswith(("ESC) Exit menu", "ESC) メニューを終了")):
        return ScreenMatch(ScreenKind.KNOWLEDGE, lines[3], 3, 0)
    # core/show-file.cpp:304-323 and knowledge/knowledge-self.cpp:201-205.
    viewer_footers = ("[Press ESC to exit.]",
        "[Press Return, Space, -, =, /, |, or ESC to exit.]",
        "[キー:(?)ヘルプ (ESC)終了]",
        "[キー:(RET/スペース)↑ (-)↓ (?)ヘルプ (ESC)終了]",
        "[キー:(RET/スペース)↓ (-)↑ (?)ヘルプ (ESC)終了]")
    title = row0.startswith("[") and row0.endswith("]") and (
        ", Line " in row0 or ("/" in row0 and "Line" not in row0))
    if title and lines[-1] in viewer_footers:
        feature = "home-inventory" if ("Home Inventory" in row0 or "我が家のアイテム" in row0) else row0
        return ScreenMatch(ScreenKind.FILE_VIEWER, feature, 0, 0)
    # cmd-visual/cmd-draw.cpp:143.
    character_footers = ("['c' to change name, 'f' to file, 'h' to change mode, or ESC]",
        "['c'で名前変更, 'f'でファイルへ書出, 'h'でモード変更, ESCで終了]")
    for y, line in enumerate(lines):
        if line in character_footers:
            return ScreenMatch(ScreenKind.CHARACTER, line, y, 0)
    # target/target-setter.cpp:196-198,434; target-describer.cpp:183,226.
    if any(template in row0 for template in ("q,t,p,o,+,-,<dir>", "q,p,o,+,-,<dir>",
                                               "q止 t決 p自 o現 +次 -前", "q止 p自 o現 +次 -前")):
        return ScreenMatch(ScreenKind.LOOK, row0, 0, 0)

    # store/cmd-store.cpp:124-151. Menu rows move together with xtra_stock.
    for menu_y in range(max(0, len(lines) - 5)):
        if lines[menu_y] not in ("You may:", "コマンド:"):
            continue
        if menu_y + 1 >= len(lines) or lines[menu_y + 1] not in (
                " ESC) Exit from Building.", " ESC) 建物から出る"):
            continue
        actions = "\n".join(lines[menu_y:min(len(lines), menu_y + 4)])
        if any(value in actions for value in ("p) Purchase an item.", "s) Sell an item.",
                "g) Get an item.", "d) Drop an item.", "p) 商品を買う", "s) アイテムを売る",
                "g) アイテムを取る", "d) アイテムを置く")):
            return ScreenMatch(ScreenKind.STORE, "complete-store-menu", menu_y, 0)
    # market/building-service.cpp:89-90,109,127,141,144.
    if len(lines) >= 24 and lines[23] in (" ESC) Exit building", " ESC) 建物を出る") \
            and lines[1].strip() and any(lines[y].startswith(" ") and ") " in lines[y]
                                         for y in range(19, 23)):
        return ScreenMatch(ScreenKind.BUILDING, "complete-building-menu", 23, 0)

    # core/player-processor.cpp:302-313; bot-screen.cpp:67-73. Supported bot UI
    # is the 80x24 main term, with the cursor on the rendered player glyph.
    width, height, cursor = screen.get("width"), screen.get("height"), screen.get("cursor")
    if width == 80 and height == 24 and len(lines) == 24 and isinstance(cursor, Mapping) \
            and not row0.endswith(":"):
        y, x = cursor.get("y"), cursor.get("x")
        if isinstance(y, int) and isinstance(x, int) and 1 <= y < 23 and 0 <= x < 80:
            cell = 0
            for char in lines[y]:
                if cell == x and char == "@":
                    return ScreenMatch(ScreenKind.COMMAND, "80x24-player-cursor", y, x)
                cell += _cell_width(char)
    return ScreenMatch(ScreenKind.UNKNOWN, "unrecognized")


@dataclass(frozen=True)
class Continuation:
    kinds: frozenset[ScreenKind]
    keys: str
    feature: str | None = None


@dataclass
class Operation:
    sequence: int | None
    owner: str
    keys: str
    observation: object
    continuations: list[Continuation] = field(default_factory=list)
    transport: Transport = Transport.TCP
    accepted_segments: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OperationResult:
    outcome: str
    operation: Operation
    board: Mapping[str, object] | None = None
    screen: ScreenMatch | None = None
    transport: KeyPostOutcome | None = None
    reason: str | None = None


class OperationExecutor:
    """Own input until ACK/post fence, fresh screen, and fresh state complete."""

    def __init__(self, client=None, *, drain: Callable[[], object] | None = None,
                 wm_post: Callable[[str], bool] | None = None) -> None:
        self.client, self.drain, self.wm_post = client, drain or (lambda: None), wm_post
        self.active: Operation | None = None
        self.ready_board: Mapping[str, object] | None = None
        self.ready_screen: ScreenMatch | None = None
        self.state = ExecutorState.AWAITING_SCREEN

    def observe_boundary(self, *, deadline: float) -> OperationResult:
        if self.client is None:
            return self._terminal(None, "bootstrap", "wm-only degraded mode", transport_name="wm-only")
        return self._observe_decidable(None, deadline)

    def submit(self, operation: Operation, *, deadline: float) -> OperationResult:
        if self.active is not None:
            return self._terminal(operation, "admission", "another operation owns input")
        if self.ready_board is None:
            return self._terminal(operation, "admission", "no fresh ready observation")
        self.ready_board = None
        self.active = operation
        return self._post_and_barrier(operation.keys, deadline)

    def _request(self, op: str, deadline: float, **fields):
        self.state = ExecutorState.AWAITING_SCREEN if op == "screen" else ExecutorState.AWAITING_STATE
        return self.client.request(op, deadline=deadline, **fields)

    def _observe_decidable(self, operation: Operation | None, deadline: float) -> OperationResult:
        screen_value = self._request("screen", deadline, term=0, attrs=False)
        if screen_value is None:
            return self._terminal(operation, "screen", "read-only request failed")
        match = classify_screen(screen_value)
        if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
            return self._terminal(operation, "classification", match.feature, match)
        screen_epoch = self.client.observation_epoch
        state = self._request("state", deadline, map=True)
        if state is None:
            return self._terminal(operation, "state", "read-only request failed", match)
        if self.client.observation_epoch != screen_epoch:
            # The state retry invalidated S. Restart S -> T within the original
            # caller deadline; the deadline selects failure, never readiness.
            return self._observe_decidable(operation, deadline)
        self.drain()
        self.ready_board, self.ready_screen, self.state = state, match, ExecutorState.READY
        holder = operation or Operation(None, "bootstrap", "", state)
        return OperationResult("ready" if operation is None else "completed", holder, state, match)

    def _post_and_barrier(self, keys: str, deadline: float) -> OperationResult:
        assert self.active is not None
        if self.active.transport is Transport.WM:
            return self._post_wm(keys, deadline)
        try:
            notation = raw_keys_to_macro_notation(keys)
        except ValueError as error:
            return self._terminal(self.active, "encoding", str(error))
        self.state = ExecutorState.AWAITING_KEYS_ACK
        outcome = self.client.post_keys(notation, expected_count=len(keys), deadline=deadline)
        if outcome.status is KeyPostStatus.REJECTED and outcome.reason == self.client.BACKPRESSURE_ERROR:
            # Atomic rejection inserted zero bytes. Re-observe the same compatible stop
            # before the sole retry, retaining the operation's original deadline.
            screen_value = self._request("screen", deadline, term=0, attrs=False)
            match = classify_screen(screen_value) if screen_value is not None else None
            if match != self.ready_screen:
                return self._terminal(self.active, "backpressure", "prompt changed before retry", match, outcome)
            self.state = ExecutorState.AWAITING_KEYS_ACK
            outcome = self.client.post_keys(notation, expected_count=len(keys), deadline=deadline)
        if outcome.status is not KeyPostStatus.ACCEPTED:
            return self._terminal(self.active, "keys", outcome.reason or outcome.status.value, transport=outcome)
        self.active.accepted_segments.append(keys)
        return self._after_post(deadline, outcome)

    def _post_wm(self, keys: str, deadline: float) -> OperationResult:
        if self.client is None or self.wm_post is None:
            return self._terminal(self.active, "wm", "wm-only degraded mode", transport_name="wm-only")
        posted = ""
        for char in keys:
            if not self.wm_post(char):
                return self._terminal(self.active, "wm-post", f"partial PostMessage prefix={posted!r}", transport_name="wm")
            posted += char
        self.active.accepted_segments.append(keys)
        self.state = ExecutorState.AWAITING_WM_FENCE
        if self.client.request("info", deadline=deadline) is None:
            return self._terminal(self.active, "wm-fence", "info request failed", transport_name="wm")
        return self._after_post(deadline, None)

    def _after_post(self, deadline: float, outcome: KeyPostOutcome | None) -> OperationResult:
        screen_value = self._request("screen", deadline, term=0, attrs=False)
        if screen_value is None:
            return self._terminal(self.active, "screen", "read-only request failed", transport=outcome)
        match = classify_screen(screen_value)
        self.state = ExecutorState.CONTINUATION
        if match.kind is ScreenKind.MORE:
            return self._post_and_barrier(" ", deadline)
        for index, continuation in enumerate(self.active.continuations):
            if match.kind in continuation.kinds and (continuation.feature is None or continuation.feature == match.feature):
                self.active.continuations.pop(index)
                return self._post_and_barrier(continuation.keys, deadline)
        if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
            return self._terminal(self.active, "continuation", f"unowned {match.kind.value}: {match.feature}", match, outcome)
        # An absent expected prompt drops its tail; it is never posted opportunistically.
        if self.active.continuations:
            return self._terminal(self.active, "continuation", "expected prompt absent", match, outcome)
        screen_epoch = self.client.observation_epoch
        state = self._request("state", deadline, map=True)
        if state is None:
            return self._terminal(self.active, "state", "read-only request failed", match, outcome)
        if self.client.observation_epoch != screen_epoch:
            # Re-establish S -> T without reposting the accepted segment.
            screen_value = self._request("screen", deadline, term=0, attrs=False)
            if screen_value is None:
                return self._terminal(self.active, "screen", "read-only retry failed", transport=outcome)
            match = classify_screen(screen_value)
            if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
                return self._terminal(self.active, "classification", match.feature, match, outcome)
            screen_epoch = self.client.observation_epoch
            state = self._request("state", deadline, map=True)
            if state is None or self.client.observation_epoch != screen_epoch:
                return self._terminal(self.active, "state", "incoherent read-only retry", match, outcome)
        self.drain()
        operation = self.active
        self.active = None
        self.ready_board, self.ready_screen, self.state = state, match, ExecutorState.READY
        return OperationResult("completed", operation, state, match, outcome)

    def _terminal(self, operation, phase, reason, screen=None, transport=None, transport_name=None):
        active = operation or self.active or Operation(None, "bootstrap", "", None)
        name = transport_name or active.transport.value
        self.active, self.ready_board, self.state = None, None, ExecutorState.TERMINAL
        request_id = transport.request_id if transport is not None else None
        status = transport.status.value if transport is not None else name
        detail = (f"<stuck-prompt> owner={active.owner} phase={phase} transport={status} "
                  f"request_id={request_id} reason={reason}")
        return OperationResult("stuck-prompt", active, None, screen, transport, detail)
