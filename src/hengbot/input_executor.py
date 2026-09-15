"""Serialized input execution at Hengband's blocking Term-read boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Mapping, Sequence
import copy
import unicodedata
import re
import time
import uuid

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
    FILE_NAME = "file-name"
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
    """Validate that state contains a player, without assuming a panel origin.

    ``cursor.cpp`` projects dungeon coordinates through the current panel and
    ``verify_panel``/``center_player`` may change that panel at any command
    boundary.  The hidden cursor and rendered ``@`` are therefore the measured,
    panel-independent evidence; state coordinates are useful only for optional
    neighbourhood corroboration when panel bounds are eventually exported.
    """
    if not isinstance(state, Mapping):
        return None
    player = state.get("player")
    if not isinstance(player, Mapping):
        return None
    y, x = player.get("y"), player.get("x")
    if not isinstance(y, int) or not isinstance(x, int):
        return None
    return None


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
                "あなたは死にました。", "あなたは壊れました。",
                "後でスコアを登録するために待機しますか？")
    for y, line in enumerate(lines):
        for literal in terminal:
            if literal in line:
                return ScreenMatch(ScreenKind.DEATH, literal, y, _cell_width(line[:line.index(literal)]))

    # cmd-visual/cmd-draw.cpp:146 keeps an 80x24
    # TermCenteredOffsetSetter active around input_status_command().  Its
    # input_string (line 112) and file_character overwrite input_check
    # therefore render logical row zero at the centered physical origin.
    # Require the complete character footer before interpreting that row: an
    # unrelated centered yes/no question is not an owned dump confirmation.
    width, height = screen.get("width"), screen.get("height")
    character_footers = (
        "['c' to change name, 'f' to file, 'h' to change mode, or ESC]",
        "['c'で名前変更, 'f'でファイルへ書出, 'h'でモード変更, ESCで終了]",
    )
    if isinstance(width, int) and isinstance(height, int) \
            and width >= 80 and height >= 24:
        cox, coy = (width - 80) // 2, (height - 24) // 2
        footer_y = coy + 23
        centered_character = footer_y < len(lines) and \
            lines[footer_y][cox:].strip() in character_footers
        if centered_character and coy < len(lines):
            prompt = lines[coy][cox:].rstrip()
            if prompt.startswith(("ファイル名: ", "File name: ")):
                return ScreenMatch(ScreenKind.FILE_NAME, prompt, coy, cox)
            if re.fullmatch(
                    r"(?:現存するファイル .+ に上書きしますか\? \[y/n\]|"
                    r"Replace existing file .+\? \[y/n\])", prompt):
                return ScreenMatch(ScreenKind.CONFIRM, prompt, coy, cox)
            if _suffix_match(prompt, ("[Y/n]", "[y/n]", "[(O)k/(C)ancel]")):
                return ScreenMatch(
                    ScreenKind.UNKNOWN, "unrecognized-centered-character-confirm",
                    coy, cox)
        if centered_character and row0.startswith(("ファイル名: ", "File name: ")):
            return ScreenMatch(ScreenKind.CHARACTER, lines[footer_y][cox:].strip(),
                               footer_y, cox + 2)

    # view/display-messages.cpp:185-207 (row zero only).
    found = _suffix_match(row0, ("-more-", "-続く-"))
    if found:
        return ScreenMatch(ScreenKind.MORE, found[0], 0, found[1])
    # core/asking-player.cpp:225-255.
    found = _suffix_match(row0, ("[Y/n]", "[y/n]", "[(O)k/(C)ancel]"))
    if found:
        return ScreenMatch(ScreenKind.CONFIRM, row0, 0, found[1])
    # cmd-visual/cmd-draw.cpp:112 calls input_string("ファイル名: ", "File name: "),
    # which core/asking-player.cpp:182-188 renders with the default on row zero.
    if row0.startswith(("ファイル名: ", "File name: ")):
        return ScreenMatch(ScreenKind.FILE_NAME, row0, 0, 0)
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
    # core/show-file.cpp:300-321 and knowledge/knowledge-self.cpp:201-205.
    # FileDisplayer installs TermCenteredOffsetSetter(MAIN_TERM_MIN_COLS, nullopt)
    # at show-file.cpp:131-135. z-term.cpp:85-90 therefore shifts logical
    # column zero by (physical width - 80) // 2 and leaves rows unshifted.
    viewer_footers = ("[Press ESC to exit.]",
        "[Press Return, Space, -, =, /, |, or ESC to exit.]",
        "[キー:(?)ヘルプ (ESC)終了]",
        "[キー:(RET/スペース)↑ (-)↓ (?)ヘルプ (ESC)終了]",
        "[キー:(RET/スペース)↓ (-)↑ (?)ヘルプ (ESC)終了]")
    if isinstance(width, int) and width >= 80 and lines:
        viewer_x = (width - 80) // 2
        viewer_title = lines[0][viewer_x:].rstrip()
        viewer_footer = lines[-1][viewer_x:].rstrip()
        # show-file.cpp:300-307 builds these title shapes. knowledge-self.cpp:
        # 201-205 supplies the exact bilingual Home caption.
        english_home_title = re.fullmatch(
            r"\[[^,\[\]]+, Home Inventory, Line \d+/\d+\]", viewer_title)
        japanese_home_title = re.fullmatch(
            r"\[[^,\[\]]+, 我が家のアイテム, \d+/\d+\]", viewer_title)
        source_title = re.fullmatch(
            r"\[[^\[\]]+, (?:Line )?\d+/\d+\]", viewer_title)
        if source_title and viewer_footer in viewer_footers:
            feature = ("home-inventory" if english_home_title or japanese_home_title
                       else viewer_title)
            return ScreenMatch(ScreenKind.FILE_VIEWER, feature, 0, viewer_x)

    # At an actual 80-column term the source-derived offset is zero.
    title = width == 80 and row0.startswith("[") and row0.endswith("]") and (
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
    feature: str | tuple[str, ...] | None = None
    exact_feature: bool = False
    optional: bool = False
    feature_pattern: bool = False


@dataclass
class Operation:
    sequence: int | None
    owner: str
    keys: str
    observation: object
    continuations: list[Continuation] = field(default_factory=list)
    response_grace: float = 0.0
    transport: Transport = Transport.TCP
    accepted_segments: list[str] = field(default_factory=list)
    business_outcome: str | None = None
    operation_reference: "OperationReference | None" = None
    accepted_segment_records: list["AcceptedSegment"] = field(default_factory=list)
    dropped_continuations: list[str] = field(default_factory=list)
    timing: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationReference:
    sequence: int | None
    owner: str
    executor_scope: str
    admission_boundary: int


@dataclass(frozen=True)
class AcceptedSegment:
    ordinal: int
    role: str
    keys: str


@dataclass(frozen=True)
class OperationReceipt:
    reference: OperationReference
    accepted_segments: tuple[AcceptedSegment, ...]
    dropped_continuations: tuple[str, ...]
    terminal_kind: str
    barrier_sequence: int
    refusal: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence": self.reference.sequence,
            "owner": self.reference.owner,
            "executor_scope": self.reference.executor_scope,
            "admission_boundary": self.reference.admission_boundary,
            "accepted_segments": [
                {"ordinal": item.ordinal, "role": item.role, "keys": item.keys}
                for item in self.accepted_segments
            ],
            "dropped_continuations": list(self.dropped_continuations),
            "terminal_kind": self.terminal_kind,
            "barrier_sequence": self.barrier_sequence,
            "refusal": self.refusal,
            "auxiliary_responses": [],
        }


SETTLEMENT_RESULTS = frozenset({
    "not-applicable", "effect-observed", "explicit-refusal",
    "no-effect-at-barrier", "partial",
})


@dataclass(frozen=True)
class PreparedIntent:
    subscriber: str
    sequence: int | None
    owner: str
    expected_keys: str
    before: object


@dataclass(frozen=True)
class AcceptedWatch:
    intent: PreparedIntent
    reference: OperationReference
    segment: AcceptedSegment


@dataclass(frozen=True)
class SettlementRecord:
    subscriber: str
    result: str
    watch: AcceptedWatch | None
    receipt: Mapping[str, object] | None


class OperationBarrierRegistry:
    """Shared prepared -> accepted -> settled operation-watch lifecycle."""

    def __init__(self) -> None:
        self._prepared: dict[str, PreparedIntent] = {}
        self._accepted: dict[str, AcceptedWatch] = {}

    def prepare(self, intent: PreparedIntent) -> None:
        self._prepared[intent.subscriber] = intent

    def cancel(self, subscriber: str) -> None:
        self._prepared.pop(subscriber, None)

    def accept(self, subscriber: str, operation: Operation,
               segment: AcceptedSegment) -> AcceptedWatch | None:
        intent = self._prepared.get(subscriber)
        reference = operation.operation_reference
        if intent is None or reference is None:
            return None
        if (intent.sequence, intent.owner) != (reference.sequence, reference.owner):
            return None
        watch = AcceptedWatch(intent, reference, segment)
        self._accepted[subscriber] = watch
        self._prepared.pop(subscriber, None)
        return watch

    def settle(self, subscriber: str, receipt: Mapping[str, object] | None,
               evaluator: Callable[[AcceptedWatch, Mapping[str, object]], str]
               ) -> SettlementRecord:
        watch = self._accepted.get(subscriber)
        if watch is None or not isinstance(receipt, Mapping):
            return SettlementRecord(subscriber, "not-applicable", watch, receipt)
        identity = (
            receipt.get("sequence"), receipt.get("owner"),
            receipt.get("executor_scope"), receipt.get("admission_boundary"),
        )
        expected = (
            watch.reference.sequence, watch.reference.owner,
            watch.reference.executor_scope, watch.reference.admission_boundary,
        )
        segments = receipt.get("accepted_segments")
        if identity != expected or not isinstance(segments, list) or not any(
            item.get("ordinal") == watch.segment.ordinal
            and item.get("keys") == watch.segment.keys
            for item in segments if isinstance(item, Mapping)
        ):
            return SettlementRecord(subscriber, "not-applicable", watch, receipt)
        result = evaluator(watch, receipt)
        if result not in SETTLEMENT_RESULTS or result == "not-applicable":
            raise ValueError(f"invalid matching settlement result: {result}")
        self._accepted.pop(subscriber, None)
        return SettlementRecord(subscriber, result, watch, receipt)


@dataclass(frozen=True)
class OperationResult:
    outcome: str
    operation: Operation
    board: Mapping[str, object] | None = None
    screen: ScreenMatch | None = None
    transport: KeyPostOutcome | None = None
    reason: str | None = None
    timing: dict[str, object] = field(default_factory=dict)


# Exact command-ending messages emitted by the device/read implementations.
# Keep this table deliberately closed: an unrelated message must never turn an
# absent owned prompt into success.  Anchors are in the sibling Hengband tree.
_ABSENT_PROMPT_MESSAGES = {
    "u": {
        "杖をうまく使えなかった。", "You failed to use the staff properly.",  # use-execution.cpp:79
        "この杖にはもう魔力が残っていない。", "The staff has no charges left.",  # :89
        "まずは杖を拾わなければ。", "You must first pick up the staffs.",  # :50
        "朦朧としていて杖を振れなかった！", "You are too stunned to use it!",  # :159
    },
    "a": {
        "魔法棒をうまく使えなかった。", "You failed to use the wand properly.",  # zapwand-execution.cpp:83
        "この魔法棒にはもう魔力が残っていない。", "The wand has no charges left.",  # :94
        "まずは魔法棒を拾わなければ。", "You must first pick up the wands.",  # :42
        "朦朧としていて魔法棒を振れなかった！", "You are too stunned to zap it!",  # :150
    },
    "z": {
        "うまくロッドを使えなかった。", "You failed to use the rod properly.",  # zaprod-execution.cpp:101
        "このロッドはまだ魔力を充填している最中だ。", "The rod is still charging.",  # :112
        "そのロッドはまだ充填中です。", "The rods are all still charging.",  # :119
        "まずはロッドを拾わなければ。", "You must first pick up the rods.",  # :49
        "朦朧としていてロッドを振れなかった！", "You are too stunned to zap it!",  # :163
    },
    "r": {
        "目が見えない。", "You can't see anything.",  # action-limited.cpp:91
        "明かりがないので見えない。", "You have no light.",  # :96
        "混乱していてできない！", "You are too confused!",  # :50
        "巻物なんて読めない。", "You cannot read.",  # read-execution.cpp:96
        "朦朧としていて読めなかった！", "You too stunned to read it!",  # :100
        "読める巻物がない。", "You have no scrolls to read.",  # cmd-read.cpp:42
    },
}
_TIMEWALK_MESSAGES = {
    "止まった時の中ではうまく働かないようだ。", "It shows no reaction.",
}  # action-limited.cpp:110; reached by all four execution paths.

# store/purchase-order.cpp:204-260.  Each message returns directly to the store
# command loop and therefore positively terminates an owned purchase prompt.
_PURCHASE_REFUSAL_MESSAGES = {
    "\u305d\u3093\u306a\u306b\u30a2\u30a4\u30c6\u30e0\u3092\u6301\u3066\u306a\u3044\u3002",
    "You cannot carry that many different items.",
    "\u30b6\u30c3\u30af\u306b\u305d\u306e\u30a2\u30a4\u30c6\u30e0\u3092\u5165\u308c\u308b\u9699\u9593\u304c\u306a\u3044\u3002",
    "You cannot carry that many items.",
    "\u304a\u91d1\u304c\u8db3\u308a\u307e\u305b\u3093\u3002",
    "You do not have enough gold.",
}

# cmd-item/cmd-equipment.cpp:229-234,383-386 and
# store/store-key-processor.cpp:269-277.  These messages return to the outer
# store command wait without applying the requested equipment mutation.
_HOME_EQUIPMENT_REFUSAL_MESSAGES = {
    "ふーむ、どうやら呪われているようだ。",
    "Hmmm, it seems to be cursed.",
    "そのコマンドは店の中では使えません。",
    "That command does not work in stores.",
}


def _unchanged_equipment_operation(operation: Operation,
                                   board: Mapping[str, object]) -> bool:
    before = operation.observation
    if not isinstance(before, Mapping):
        return False
    return (
        before.get("inventory") == board.get("inventory")
        and before.get("equipment") == board.get("equipment")
    )

def _operation_messages(screen: Mapping[str, object], board: Mapping[str, object]) -> list[str]:
    """Return only evidence obtained at this operation's successful barrier."""
    rows = screen.get("lines", ())
    messages = [str(rows[0]).rstrip()] if isinstance(rows, Sequence) and rows else []
    delta = board.get("messages", ())
    if isinstance(delta, Sequence) and not isinstance(delta, (str, bytes)):
        messages.extend(str(message).rstrip() for message in delta)
    return [message for message in messages if message]


def _expected_prompt_absence_is_complete(
        operation: Operation, screen: Mapping[str, object], board: Mapping[str, object]) -> bool:
    """Classify only source-proven terminal outcomes for an unused tail."""
    command = operation.accepted_segments[0][:1] if operation.accepted_segments else operation.keys[:1]
    if command not in _ABSENT_PROMPT_MESSAGES:
        return False
    endings = _ABSENT_PROMPT_MESSAGES.get(command, set()) | _TIMEWALK_MESSAGES
    if any(message in endings for message in _operation_messages(screen, board)):
        return True

    # Full-identify may legitimately omit the target prompt when the bound
    # target is already known, or after its selected one-shot source vanishes.
    # Compare the operation's originating board with this barrier state; a
    # mere command boundary or unchanged board is not positive evidence.
    if not operation.owner.startswith("identify:full"):
        return False
    before = operation.observation if isinstance(operation.observation, Mapping) else {}
    before_items = {
        str(item.get("slot")): item for item in before.get("inventory", ())
        if isinstance(item, Mapping)
    }
    after_items = {
        str(item.get("slot")): item for item in board.get("inventory", ())
        if isinstance(item, Mapping)
    }
    pending = operation.continuations[0] if operation.continuations else None
    if pending is not None and ScreenKind.ITEM_TARGET in pending.kinds:
        old_target = before_items.get(pending.keys[:1])
        target = after_items.get(pending.keys[:1])
        if old_target is not None and not bool(old_target.get("fully_known")) \
                and target is not None and bool(target.get("fully_known")):
            return True
    accepted_source = operation.accepted_segments[-1][:1] if len(operation.accepted_segments) > 1 else ""
    if accepted_source and accepted_source in before_items:
        old = before_items[accepted_source]
        identity = tuple(old.get(key) for key in ("tval", "sval", "name"))
        old_count = sum(
            int(item.get("count", 0)) for item in before_items.values()
            if tuple(item.get(key) for key in ("tval", "sval", "name")) == identity
        )
        new_count = sum(
            int(item.get("count", 0)) for item in after_items.values()
            if tuple(item.get(key) for key in ("tval", "sval", "name")) == identity
        )
        if new_count < old_count:
            return True
    return False


def _same_barrier_value(
        state: Mapping[str, object], record: Mapping[str, object], key: str) -> bool:
    """Compare emitter values that bind a store record to the TCP state stop."""
    return key in state and key in record and state[key] == record[key]


def compose_barrier_board(
        state: Mapping[str, object], screen: Mapping[str, object], kind: ScreenKind,
        records: Iterable[Mapping[str, object]],
        timing: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, list[Mapping[str, object]]]:
    """Build the sole policy board and preserve the physical observation order.

    TCP ``state`` is the base.  JSONL contributes only unread message diffs and,
    at a store command stop, the last fully bound current-page store payload.
    State HISTORY is deliberately not copied into the policy message delta.
    """
    compose_started = time.perf_counter()
    ordered = [record for record in records if isinstance(record, Mapping)]
    deepcopy_started = time.perf_counter()
    board = copy.deepcopy(dict(state))
    deepcopy_ms = (time.perf_counter() - deepcopy_started) * 1000
    messages: list[str] = []
    for record in ordered:
        raw = record.get("messages", ())
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            messages.extend(str(message) for message in raw)
    board["messages"] = messages
    if kind is not ScreenKind.STORE:
        board.pop("store", None)
        if timing is not None:
            timing["state_deepcopy_ms"] += deepcopy_ms
            timing["board_compose_ms"] += max(
                0.0, (time.perf_counter() - compose_started) * 1000 - deepcopy_ms)
        return board, ordered

    candidates = [
        record for record in ordered
        if isinstance(record.get("store"), Mapping)
    ]
    if not candidates:
        return None, ordered
    candidate = candidates[-1]
    # These whole structures include floor/town/location, inventory/equipment,
    # gold, turn, and any page identity exported by either endpoint.
    required = ("floor", "player", "inventory", "equipment", "turn")
    if not all(_same_barrier_value(state, candidate, key) for key in required):
        return None, ordered
    store = candidate["store"]
    state_store = state.get("store")
    if isinstance(state_store, Mapping):
        for key in ("store_type", "page", "page_index", "visible_start"):
            if key in state_store and state_store.get(key) != store.get(key):
                return None, ordered
    visible = "\n".join(str(line) for line in screen.get("lines", ()))
    items = store.get("items", ())
    if isinstance(items, Sequence) and items:
        names = [str(item.get("name", "")) for item in items if isinstance(item, Mapping)]
        if names and not any(name and name in visible for name in names):
            return None, ordered
    deepcopy_started = time.perf_counter()
    board["store"] = copy.deepcopy(store)
    deepcopy_ms += (time.perf_counter() - deepcopy_started) * 1000
    if timing is not None:
        timing["state_deepcopy_ms"] += deepcopy_ms
        timing["board_compose_ms"] += max(
            0.0, (time.perf_counter() - compose_started) * 1000 - deepcopy_ms)
    return board, ordered


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
        self.ready_screen_value: Mapping[str, object] | None = None
        self._bound_screen_value: Mapping[str, object] | None = None
        self._bound_state_value: Mapping[str, object] | None = None
        self.barrier_sequence = 0
        self.executor_scope = uuid.uuid4().hex
        self.state = ExecutorState.AWAITING_SCREEN

    @staticmethod
    def _new_timing() -> dict[str, object]:
        return {
            "ack_wait_ms": 0.0, "screen_wait_ms": 0.0,
            "screen_classification_ms": 0.0, "state_wait_ms": 0.0,
            "jsonl_drain_ms": 0.0, "jsonl_drain_bytes": 0,
            "jsonl_drain_records": 0, "jsonl_decode_ms": 0.0,
            "state_deepcopy_ms": 0.0, "board_compose_ms": 0.0,
            "posting_contract_settlement_ms": 0.0, "segments": 0,
            "requests": 0, "observation_epoch_refreshes": 0,
            "retry_send_added": False, "post_ack_grace_extended": False,
            "known_cells": 0, "request_first_byte_ms": 0.0,
            "first_last_byte_ms": 0.0, "request_json_decode_ms": 0.0,
            "response_bytes": 0, "control_requests": [],
        }

    def _classify(self, screen, state=None):
        started = time.perf_counter()
        result = classify_screen(screen, state)
        if self.active is not None:
            self.active.timing["screen_classification_ms"] += \
                (time.perf_counter() - started) * 1000
        return result

    def _finish_board(self, state, screen_value, match):
        started = time.perf_counter()
        records = self.drain()
        drained_at = time.perf_counter()
        if records is None:
            records = ()
        timing = self.active.timing if self.active is not None else None
        if timing is not None:
            timing["jsonl_drain_ms"] += (drained_at - started) * 1000
            timing["jsonl_drain_records"] += len(records)
            drain_timing = getattr(self.drain, "last_timing", {})
            timing["jsonl_drain_bytes"] += int(drain_timing.get("bytes", 0))
            timing["jsonl_decode_ms"] += float(drain_timing.get("decode_ms", 0.0))
        board, _ordered = compose_barrier_board(
            state, screen_value, match.kind, records, timing)
        if board is None:
            return None
        if timing is not None:
            grid_map = board.get("grid_map", {})
            palette = grid_map.get("palette", ()) if isinstance(grid_map, Mapping) else ()
            timing["known_cells"] = sum(
                int(run[2]) for run in grid_map.get("runs", ())
                if isinstance(run, Sequence) and len(run) >= 4
                and isinstance(run[3], int) and run[3] < len(palette)
                and isinstance(palette[run[3]], Sequence) and len(palette[run[3]]) >= 4
                and bool(palette[run[3]][3])
            ) if isinstance(grid_map, Mapping) else 0
        return board

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
        operation.operation_reference = OperationReference(
            operation.sequence, operation.owner, self.executor_scope,
            self.barrier_sequence,
        )
        self.active = operation
        operation.timing = self._new_timing()
        if hasattr(self.client, "start_request_timings"):
            self.client.start_request_timings()
        return self._post_and_barrier(operation.keys, deadline, role="transaction")

    def _request(self, op: str, deadline: float, **fields):
        self.state = ExecutorState.AWAITING_SCREEN if op == "screen" else ExecutorState.AWAITING_STATE
        started = time.perf_counter()
        result = self.client.request(
            op, deadline=deadline, retry_until_deadline=True, **fields
        )
        if self.active is not None:
            self.active.timing[f"{op}_wait_ms"] += (time.perf_counter() - started) * 1000
        return result

    def _observe_decidable(self, operation: Operation | None, deadline: float) -> OperationResult:
        screen_value = self._request("screen", deadline, term=0, attrs=False)
        if screen_value is None:
            return self._terminal(operation, "screen", "read-only request failed")
        match = self._classify(screen_value)
        if match.kind is ScreenKind.DEATH:
            return self._death(operation, match)
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
        match = self._classify(screen_value, state)
        if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
            return self._terminal(operation, "classification", match.feature, match)
        board = self._finish_board(state, screen_value, match)
        if board is None:
            return self._terminal(
                operation, "store-state",
                "missing or mismatching current store page", match)
        self.ready_board, self.ready_screen, self.ready_screen_value, self.state = (
            board, match, screen_value, ExecutorState.READY)
        self.barrier_sequence += 1
        self._bound_screen_value, self._bound_state_value = screen_value, state
        holder = operation or Operation(None, "bootstrap", "", state)
        return OperationResult("ready" if operation is None else "completed", holder, board, match)

    def _post_and_barrier(self, keys: str, deadline: float, *, role: str = "answer") -> OperationResult:
        assert self.active is not None
        if self.active.transport is Transport.WM:
            return self._post_wm(keys, deadline, role=role)
        try:
            notation = raw_keys_to_macro_notation(keys)
        except ValueError as error:
            return self._terminal(self.active, "encoding", str(error))
        self.state = ExecutorState.AWAITING_KEYS_ACK
        ack_started = time.perf_counter()
        outcome = self.client.post_keys(notation, expected_count=len(keys), deadline=deadline)
        self.active.timing["ack_wait_ms"] += (time.perf_counter() - ack_started) * 1000
        if outcome.status is KeyPostStatus.REJECTED and outcome.reason == self.client.BACKPRESSURE_ERROR:
            # Atomic rejection inserted zero bytes. Re-observe the screen and the
            # state-bound item/operation premise before the sole retry, retaining
            # the operation's original deadline (spec section 4 backpressure row).
            screen_value = self._request("screen", deadline, term=0, attrs=False)
            match = self._classify(screen_value) if screen_value is not None else None
            state_value = self._request("state", deadline, map=True) if match is not None else None
            rebound = self._classify(screen_value, state_value) \
                if screen_value is not None and state_value is not None else None
            if screen_value != self._bound_screen_value \
                    or state_value != self._bound_state_value \
                    or rebound != match:
                return self._terminal(self.active, "backpressure", "prompt changed before retry", match, outcome)
            self.state = ExecutorState.AWAITING_KEYS_ACK
            self.active.timing["retry_send_added"] = True
            ack_started = time.perf_counter()
            outcome = self.client.post_keys(notation, expected_count=len(keys), deadline=deadline)
            self.active.timing["ack_wait_ms"] += (time.perf_counter() - ack_started) * 1000
        if outcome.status is not KeyPostStatus.ACCEPTED:
            return self._terminal(self.active, "keys", outcome.reason or outcome.status.value, transport=outcome)
        self.active.accepted_segments.append(keys)
        self.active.timing["segments"] += 1
        self.active.accepted_segment_records.append(AcceptedSegment(
            len(self.active.accepted_segment_records), role, keys,
        ))
        self.accepted(self.active, keys)
        observation_deadline = max(
            deadline, time.monotonic() + self.active.response_grace
        )
        self.active.timing["post_ack_grace_extended"] = bool(
            self.active.timing["post_ack_grace_extended"]
        ) or observation_deadline > deadline
        return self._after_post(observation_deadline, outcome)

    def _post_wm(self, keys: str, deadline: float, *, role: str) -> OperationResult:
        if self.client is None or self.wm_post is None:
            return self._terminal(self.active, "wm", "wm-only degraded mode", transport_name="wm-only")
        posted = ""
        for char in keys:
            if not self.wm_post(char):
                return self._terminal(self.active, "wm-post", f"partial PostMessage prefix={posted!r}", transport_name="wm")
            posted = posted + char
        self.active.accepted_segments.append(keys)
        self.active.accepted_segment_records.append(AcceptedSegment(
            len(self.active.accepted_segment_records), role, keys,
        ))
        self.accepted(self.active, keys)
        self.state = ExecutorState.AWAITING_WM_FENCE
        if self.client.request("info", deadline=deadline) is None:
            return self._terminal(self.active, "wm-fence", "info request failed", transport_name="wm")
        return self._after_post(deadline, None)

    def _after_post(self, deadline: float, outcome: KeyPostOutcome | None) -> OperationResult:
        screen_value = self._request("screen", deadline, term=0, attrs=False)
        if screen_value is None:
            return self._terminal(self.active, "screen", "read-only request failed", transport=outcome)
        match = self._classify(screen_value)
        self.state = ExecutorState.CONTINUATION
        if match.kind is ScreenKind.DEATH:
            return self._death(self.active, match)
        if match.kind is ScreenKind.MORE:
            return self._post_and_barrier(" ", deadline, role="auxiliary-request")
        if self.active.owner.startswith("identify:full"):
            if match.kind is ScreenKind.IDENTIFY_VIEWER_PAGE:
                # screen_object() owns an arbitrary number of attribute pages.
                return self._post_and_barrier(" ", deadline, role="auxiliary-request")
            if match.kind is ScreenKind.IDENTIFY_VIEWER_FINAL:
                return self._post_and_barrier("\x1b", deadline, role="exit")
        while self.active.continuations:
            continuation = self.active.continuations[0]
            expected_features = (
                continuation.feature
                if isinstance(continuation.feature, tuple)
                else (continuation.feature,)
            )
            feature_matches = continuation.feature is None or any(
                (continuation.feature_pattern and re.fullmatch(feature, match.feature) is not None)
                or match.feature == feature
                or (
                    not continuation.exact_feature
                    and match.feature.rstrip().endswith(feature.rstrip())
                )
                for feature in expected_features if feature is not None
            )
            if match.kind in continuation.kinds and feature_matches:
                prompt_state = self._request("state", deadline, map=True)
                if prompt_state is None:
                    return self._terminal(self.active, "state", "prompt binding failed", match, outcome)
                self._bound_screen_value, self._bound_state_value = screen_value, prompt_state
                self.active.continuations.pop(0)
                return self._post_and_barrier(continuation.keys, deadline, role="answer")
            if continuation.optional:
                self.active.continuations.pop(0)
                continue
            break
        if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
            return self._terminal(self.active, "continuation", f"unowned {match.kind.value}: {match.feature}", match, outcome)
        screen_epoch = self.client.observation_epoch
        state = self._request("state", deadline, map=True)
        if state is None:
            return self._terminal(self.active, "state", "read-only request failed", match, outcome)
        if self.client.observation_epoch != screen_epoch:
            self.active.timing["observation_epoch_refreshes"] += 1
            # Re-establish S -> T without reposting the accepted segment.
            screen_value = self._request("screen", deadline, term=0, attrs=False)
            if screen_value is None:
                return self._terminal(self.active, "screen", "read-only retry failed", transport=outcome)
            match = self._classify(screen_value)
            if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
                return self._terminal(self.active, "classification", match.feature, match, outcome)
            screen_epoch = self.client.observation_epoch
            state = self._request("state", deadline, map=True)
            if state is None or self.client.observation_epoch != screen_epoch:
                return self._terminal(self.active, "state", "incoherent read-only retry", match, outcome)
        match = self._classify(screen_value, state)
        if match.kind not in (ScreenKind.COMMAND, ScreenKind.STORE):
            return self._terminal(self.active, "classification", match.feature, match, outcome)
        board = self._finish_board(state, screen_value, match)
        if board is None:
            return self._terminal(
                self.active, "store-state",
                "missing or mismatching current store page", match, outcome)
        if self.active.owner == "shop:one-shot-buy" and any(
                message in _PURCHASE_REFUSAL_MESSAGES
                for message in _operation_messages(screen_value, board)):
            self.active.business_outcome = "failed:purchase-refused"
            self.active.dropped_continuations.extend(
                item.keys for item in self.active.continuations
            )
            self.active.continuations.clear()
            if match.kind is ScreenKind.STORE:
                return self._post_and_barrier("\x1b", deadline, role="exit")
        if (
            self.active.owner.startswith("equipment-transaction:")
            and match.kind is ScreenKind.STORE
            and _unchanged_equipment_operation(self.active, board)
            and any(
                message in _HOME_EQUIPMENT_REFUSAL_MESSAGES
                for message in _operation_messages(screen_value, board)
            )
        ):
            self.active.business_outcome = "refused"
        # Spec section 4: at a successful command/store barrier an unused tail
        # is dropped only when fresh effects positively establish that the
        # source command ended.  Ambiguous absence remains a visible terminal.
        if self.active.continuations:
            if not _expected_prompt_absence_is_complete(
                    self.active, screen_value, board):
                return self._terminal(
                    self.active, "continuation", "expected prompt absent",
                    match, outcome)
            self.active.dropped_continuations.extend(
                item.keys for item in self.active.continuations
            )
            self.active.continuations.clear()
        operation = self.active
        # Decision-only provenance: this board was obtained by the causal
        # screen/state barrier following this exact accepted operation.  JSONL
        # observations and bootstrap boards deliberately never carry it.
        board["_completed_operation_sequence"] = operation.sequence
        board["_completed_operation_owner"] = operation.owner
        assert operation.operation_reference is not None
        receipt = OperationReceipt(
            operation.operation_reference,
            tuple(operation.accepted_segment_records),
            tuple(operation.dropped_continuations),
            match.kind.value,
            self.barrier_sequence + 1,
            operation.business_outcome,
        )
        board["_completed_operation_receipt"] = receipt.as_dict()
        self.active = None
        self.ready_board, self.ready_screen, self.ready_screen_value, self.state = (
            board, match, screen_value, ExecutorState.READY)
        self.barrier_sequence += 1
        request_timings = self.client.take_request_timings() \
            if hasattr(self.client, "take_request_timings") else []
        grouped: list[dict[str, object]] = []
        for item in request_timings:
            if not grouped or grouped[-1]["request"] != item["request"]:
                grouped.append({
                    "request": item["request"], "kind": item["kind"],
                    "attempt_count": 0, "connect_count": 0,
                    "retry_count": 0, "response_bytes": 0, "attempts": [],
                })
            request = grouped[-1]
            request["attempt_count"] += 1
            request["connect_count"] += int(bool(item["connected"]))
            request["retry_count"] = max(
                int(request["retry_count"]), int(item["retry_count"])
            )
            request["response_bytes"] += int(item["response_bytes"])
            request["attempts"].append({
                key: item[key] for key in (
                    "request_first_byte_ms", "first_last_byte_ms",
                    "json_decode_ms", "response_bytes", "connected",
                )
            })
        operation.timing["requests"] = len(grouped)
        operation.timing["control_requests"] = grouped[:12]
        operation.timing["request_first_byte_ms"] = sum(
            float(item["request_first_byte_ms"]) for item in request_timings)
        operation.timing["first_last_byte_ms"] = sum(
            float(item["first_last_byte_ms"]) for item in request_timings)
        operation.timing["request_json_decode_ms"] = sum(
            float(item["json_decode_ms"]) for item in request_timings)
        operation.timing["response_bytes"] = sum(
            int(item["response_bytes"]) for item in request_timings)
        for key, value in tuple(operation.timing.items()):
            if key.endswith("_ms") and isinstance(value, float):
                operation.timing[key] = round(value, 3)
        return OperationResult(
            "completed", operation, board, match, outcome,
            timing=operation.timing,
        )

    def _terminal(self, operation, phase, reason, screen=None, transport=None, transport_name=None):
        active = operation or self.active or Operation(None, "bootstrap", "", None)
        name = transport_name or active.transport.value
        self.active, self.ready_board, self.ready_screen, self.ready_screen_value, self.state = (
            None, None, None, None, ExecutorState.TERMINAL)
        request_id = transport.request_id if transport is not None else None
        status = transport.status.value if transport is not None else name
        detail = (f"<stuck-prompt> owner={active.owner} phase={phase} transport={status} "
                  f"request_id={request_id} reason={reason}")
        return OperationResult("stuck-prompt", active, None, screen, transport, detail)

    def _death(self, operation, screen):
        active = operation or self.active or Operation(None, "bootstrap", "", None)
        self.active, self.ready_board, self.ready_screen, self.ready_screen_value, self.state = (
            None, None, None, None, ExecutorState.TERMINAL)
        return OperationResult(
            "player-death", active, None, screen,
            reason=f"<player-death> feature={screen.feature}",
        )
