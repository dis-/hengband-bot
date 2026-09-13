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


def _char_at_cell(row: str, column: int) -> str | None:
    cell = 0
    for char in row:
        if cell == column:
            return char
        cell += _cell_width(char)
        if cell > column:
            return None
    return None


def _state_player_matches_cursor(
        state: Mapping[str, object] | None, cursor_x: int, cursor_y: int) -> bool | None:
    """Corroborate rendered coordinates without consulting sparse map glyphs.

    The main map starts at COL_MAP=12 (main-window-row-column.h:72-73).
    An entrance, object, or monster may occupy the state player's cell, and
    sparse cells need not carry a glyph at all.
    """
    if not isinstance(state, Mapping):
        return None
    player = state.get("player")
    if not isinstance(player, Mapping):
        return None
    y, x = player.get("y"), player.get("x")
    if not isinstance(y, int) or not isinstance(x, int):
        return None
    return cursor_x == x + 12 and cursor_y == y


def classify_screen(screen: Mapping[str, object], state: Mapping[str, object] | None = None) -> ScreenMatch:
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
    if re.search(r"(?:Quantity \(1-|いくつですか \(1-)\d+\):(?: .*)?$", row0) or \
            re.search(r"^(?:Rest|休憩) \(0-9999, .+\):(?: .*)?$", row0):
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
    # store/store.cpp:181-185. Japanese selects either 商品 or アイテム.
    if re.match(r"^\((?:商品|アイテム):.-., ESCで中断\) ", row0):
        return ScreenMatch(ScreenKind.ITEM_SOURCE, row0, 0, 0)

    # perception/identification.cpp:762-799. prt() starts at x=15 and the
    # heading literal itself begins with five spaces, so its text starts at 20.
    attr_rows = [(y, line) for y, line in enumerate(lines)
                 if line.startswith(" " * 20 + "Item Attributes:") or
                 line.startswith(" " * 20 + "アイテムの能力:")]
    if attr_rows:
        for y, line in enumerate(lines):
            if line.startswith(" " * 15 + "-- more --") or line.startswith(" " * 15 + "-- 続く --"):
                return ScreenMatch(ScreenKind.IDENTIFY_VIEWER_PAGE, line.strip(), y, 15)
            if line.startswith(" " * 15 + "[Press any key to continue]") or line.startswith(" " * 15 + "[何かキーを押すとゲームに戻ります]"):
                return ScreenMatch(ScreenKind.IDENTIFY_VIEWER_FINAL, line.strip(), y, 15)
        return ScreenMatch(ScreenKind.UNKNOWN, "incomplete-identify-viewer")

    # cmd-knowledge.cpp:32 centers the 80x24 logical term in both directions;
    # literals remain at logical rows 3, 20 and 21 (lines 36, 63, 66).
    width, height = screen.get("width"), screen.get("height")
    if isinstance(width, int) and isinstance(height, int) and width >= 80 and height >= 24:
        kox, koy = (width - 80) // 2, (height - 24) // 2
        if koy + 21 < len(lines) \
                and lines[koy + 3][kox:].startswith(("Display current knowledge", "現在の知識を確認する")) \
                and lines[koy + 20][kox:].startswith(("Command:", "コマンド:")) \
                and lines[koy + 21][kox:].startswith((" ESC) Exit menu", " ESC) 抜ける")):
            return ScreenMatch(ScreenKind.KNOWLEDGE, lines[koy + 3][kox:].strip(), koy + 3, kox)
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
        if line.strip() in character_footers:
            return ScreenMatch(ScreenKind.CHARACTER, line.strip(), y,
                               _cell_width(line) - _cell_width(line.lstrip()))
    # target/target-setter.cpp:196-198,434; target-describer.cpp:183,226.
    if any(template in row0 for template in (
            "q,t,p,o,+,-,<dir>", "q,p,o,+,-,<dir>",
            "q止 t決 p自 o現 +次 -前", "q止 p自 o現 +次 -前",
            "[q止 p自 o現 +次 -前 g移]")):
        return ScreenMatch(ScreenKind.LOOK, row0, 0, 0)

    # unverified-live: store/cmd-store.cpp:58-60,123-151; z-term.cpp:89-103.
    # Stores use a
    # centered logical width of 80, full physical height, and height-derived
    # xtra_stock. Several commands intentionally share each physical row.
    if isinstance(width, int) and isinstance(height, int) and width >= 80 and height >= 24:
        menu_y = 20 + min(40, height - 24)
        offset_x = (width - 80) // 2
        command = lines[menu_y][offset_x:] if menu_y < len(lines) else ""
        exit_row = lines[menu_y + 1][offset_x:] if menu_y + 1 < len(lines) else ""
        actions = "\n".join(line[offset_x:] for line in lines[menu_y:min(len(lines), menu_y + 4)])
        complete = command.startswith(("You may:", "コマンド:")) and exit_row.startswith((
            " ESC) Exit from Building.", " ESC) 建物から出る"))
    else:
        menu_y, offset_x, actions, complete = 0, 0, "", False
    if complete:
        if any(value in actions for value in ("p) Purchase an item.", "s) Sell an item.",
                "g) Get an item.", "d) Drop an item.", "p) 商品を買う", "s) アイテムを売る",
                "g) アイテムを取る", "d) アイテムを置く")):
            return ScreenMatch(ScreenKind.STORE, "complete-store-menu", menu_y, offset_x)
    # unverified-live: market/building-service.cpp:89-90,109,127,141,144 and
    # cmd-building/cmd-building.cpp:342: logical 80x24 is centered both ways.
    if isinstance(width, int) and isinstance(height, int) and width >= 80 and height >= 24:
        ox, oy = (width - 80) // 2, (height - 24) // 2
        if oy + 23 < len(lines) and lines[oy + 23][ox:].startswith((
                " ESC) Exit building", " ESC) 建物を出る")) \
                and lines[oy + 2][ox:].strip() \
                and any(") " in lines[y][ox:] for y in range(oy + 19, oy + 23)):
            return ScreenMatch(ScreenKind.BUILDING, "complete-building-menu", oy + 23, ox)

    # core/player-processor.cpp:302-313; window/main-window-util.h:7-8;
    # main-window-row-column.h:72-73; main-window-left-frame.cpp:168-181.
    # Map cells begin after COL_MAP=12 and depth is at (width-8,height-1).
    # Real Windows command waits hide the cursor; all captured modal/prompt
    # screens show it. Visibility corroborates '@', layout, and fresh state.
    cursor = screen.get("cursor")
    if isinstance(width, int) and isinstance(height, int) and width >= 80 and height >= 24 \
            and len(lines) == height and isinstance(cursor, Mapping) \
            and cursor.get("visible") is False:
        y, x = cursor.get("y"), cursor.get("x")
        status = any(lines[row][:12].strip() for row in range(1, min(15, height - 1)))
        depth = lines[height - 1]
        depth_anchor = bool(depth.strip()) and _cell_width(depth) >= width - 8
        corroborated = _state_player_matches_cursor(state, x, y) \
            if isinstance(x, int) and isinstance(y, int) else None
        if isinstance(y, int) and isinstance(x, int) and 1 <= y < height - 1 and 12 < x < width - 1 \
                and status and depth_anchor and _char_at_cell(lines[y], x) == "@" and corroborated is not False:
            return ScreenMatch(ScreenKind.COMMAND, "layout-player-cursor", y, x)
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
                 wm_post: Callable[[str], bool] | None = None,
                 accepted: Callable[[Operation, str], None] | None = None) -> None:
        self.client, self.drain, self.wm_post = client, drain or (lambda: None), wm_post
        self.accepted = accepted or (lambda _operation, _segment: None)
        self.active: Operation | None = None
        self.ready_board: Mapping[str, object] | None = None
        self.ready_screen: ScreenMatch | None = None
        self._bound_screen_value: Mapping[str, object] | None = None
        self._bound_state_value: Mapping[str, object] | None = None
        self.state = ExecutorState.AWAITING_SCREEN

    def observe_boundary(self, *, deadline: float) -> OperationResult:
        if self.client is None:
            return self._terminal(None, "bootstrap", "wm-only degraded mode", transport_name="wm-only")
        return self._observe_decidable(None, deadline)

    def submit(self, operation: Operation, *, deadline: float) -> OperationResult:
        if self.active is not None:
            # Admission refusal must never retire or poison the owning operation.
            # This is the causal gate used by every producer, not merely a check
            # immediately in front of the transport.
            return OperationResult(
                "busy", operation, reason=f"input owned by {self.active.owner}"
            )
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
        match = classify_screen(screen_value, state)
        if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
            return self._terminal(operation, "classification", match.feature, match)
        self.drain()
        self.ready_board, self.ready_screen, self.state = state, match, ExecutorState.READY
        self._bound_screen_value, self._bound_state_value = screen_value, state
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
            # Atomic rejection inserted zero bytes. Re-observe the screen and the
            # state-bound item/operation premise before the sole retry, retaining
            # the operation's original deadline (spec section 4 backpressure row).
            screen_value = self._request("screen", deadline, term=0, attrs=False)
            match = classify_screen(screen_value) if screen_value is not None else None
            state_value = self._request("state", deadline, map=True) if match is not None else None
            rebound = classify_screen(screen_value, state_value) \
                if screen_value is not None and state_value is not None else None
            if screen_value != self._bound_screen_value \
                    or state_value != self._bound_state_value \
                    or rebound != match:
                return self._terminal(self.active, "backpressure", "prompt changed before retry", match, outcome)
            self.state = ExecutorState.AWAITING_KEYS_ACK
            outcome = self.client.post_keys(notation, expected_count=len(keys), deadline=deadline)
        if outcome.status is not KeyPostStatus.ACCEPTED:
            return self._terminal(self.active, "keys", outcome.reason or outcome.status.value, transport=outcome)
        self.active.accepted_segments.append(keys)
        self.accepted(self.active, keys)
        return self._after_post(deadline, outcome)

    def _post_wm(self, keys: str, deadline: float) -> OperationResult:
        if self.client is None or self.wm_post is None:
            return self._terminal(self.active, "wm", "wm-only degraded mode", transport_name="wm-only")
        posted = ""
        for char in keys:
            if not self.wm_post(char):
                return self._terminal(self.active, "wm-post", f"partial PostMessage prefix={posted!r}", transport_name="wm")
            posted = posted + char
        self.active.accepted_segments.append(keys)
        self.accepted(self.active, keys)
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
        if self.active.continuations:
            continuation = self.active.continuations[0]
            feature_matches = (
                continuation.feature is None
                or match.feature == continuation.feature
                or match.feature.rstrip().endswith(continuation.feature.rstrip())
            )
            if match.kind in continuation.kinds and feature_matches:
                prompt_state = self._request("state", deadline, map=True)
                if prompt_state is None:
                    return self._terminal(self.active, "state", "prompt binding failed", match, outcome)
                self._bound_screen_value, self._bound_state_value = screen_value, prompt_state
                self.active.continuations.pop(0)
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
        match = classify_screen(screen_value, state)
        if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
            return self._terminal(self.active, "classification", match.feature, match, outcome)
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
