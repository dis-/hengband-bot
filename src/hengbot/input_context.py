"""The one reader of the game's published input context (slice S0: record only).

Since Hengband develop 04e95fb52c the control server attaches
``result.input_context`` to every successful ``screen`` and ``state`` reply
(tools/bot/README.md "input_context").  A reply answers only while the key
queue is empty, so a context describes the input wait that consumed every
injected key (plans/DESIGN-control-context-1022.md section 2).

Four states, never confused (design section 6.1):

* ``unavailable`` -- no reply, an error reply, or a value of the wrong shape;
* ``absent``      -- a successful reply without the key (an older game);
* ``null``        -- the game waits without publishing its context (character
  sheet, file viewer, building menu ...).  ``null`` does not mean "no wait";
* ``server``      -- the published object (``kind``, ``prompt``, details).

Slice S0 decides nothing from the context.  ``current_input_state`` returns the
screen classifier's own match unchanged and only adds the reading and a
comparison verdict; :class:`InputContextShadow` records the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping
import json
import os

from hengbot.flight_recorder import rotate_log
from hengbot.input_executor import ScreenKind, ScreenMatch, classify_screen


INPUT_CONTEXT_SHADOW_NAME = "input-context-shadow.jsonl"
# Design section 6.3: the shadow log rotates itself at 8 MB (one predecessor
# is kept); the soak runner's ROTATE_LOGS must not rotate it a second time.
INPUT_CONTEXT_SHADOW_ROTATE_BYTES = 8 * 1024**2

Source = Literal["unavailable", "absent", "null", "server"]


@dataclass(frozen=True)
class InputContextReading:
    source: Source
    kind: str | None = None
    prompt: str = ""
    details: Mapping[str, object] = field(default_factory=dict)
    note: str = ""

    @property
    def label(self) -> str:
        """``ctx=`` value: the published kind, else the source state."""
        return self.kind if self.source == "server" and self.kind else self.source

    def as_dict(self) -> dict[str, object]:
        row: dict[str, object] = {"source": self.source}
        if self.source == "server":
            row.update({"kind": self.kind, "prompt": self.prompt})
            if self.details:
                row["details"] = dict(self.details)
        if self.note:
            row["note"] = self.note
        return row


def read_input_context(reply: object) -> InputContextReading:
    """Read one ``screen``/``state`` result; never raises.

    ``reply`` is the ``result`` object of a successful request (what
    ``ControlClient.request`` returns), or ``None`` when the request failed.
    """
    if reply is None:
        return InputContextReading("unavailable", note="no reply")
    if not isinstance(reply, Mapping):
        return InputContextReading("unavailable", note="reply is not an object")
    if "input_context" not in reply:
        return InputContextReading("absent")
    value = reply["input_context"]
    if value is None:
        return InputContextReading("null")
    if not isinstance(value, Mapping):
        return InputContextReading("unavailable", note="input_context is not an object")
    kind, prompt = value.get("kind"), value.get("prompt", "")
    if not isinstance(kind, str) or not kind or not isinstance(prompt, str):
        return InputContextReading("unavailable", note="input_context has no kind")
    details = {key: item for key, item in value.items() if key not in {"kind", "prompt"}}
    return InputContextReading("server", kind, prompt, details)


def read_input_view(reply: Mapping[str, object]) -> tuple[InputContextReading, tuple[str, ...]]:
    """Pair context and rendered rows from one reply, without a second read.

    Magic-Eater's raw inkey type menu publishes null; its cursor and charges
    therefore need the rows accompanying that same context observation.
    Keep access to both observations in the established input reader.
    """
    raw = reply.get("lines", ())
    rows = tuple(str(line).rstrip() for line in raw) if isinstance(raw, (list, tuple)) else ()
    return read_input_context(reply), rows


# Design section 6.1 table: the screen kinds a published context admits.  The
# open kinds (command_char, string, any_key, point) also admit UNKNOWN, which
# is what the design maps their unlisted prompts to.
_COMPATIBLE_KINDS: dict[str, frozenset[ScreenKind]] = {
    "confirm": frozenset({ScreenKind.CONFIRM}),
    "quantity": frozenset({ScreenKind.QUANTITY}),
    "more": frozenset({ScreenKind.MORE}),
    "item": frozenset({ScreenKind.ITEM_SOURCE, ScreenKind.ITEM_TARGET}),
    "direction": frozenset({ScreenKind.DIRECTION}),
    "target": frozenset({ScreenKind.LOOK}),
    "command_char": frozenset({ScreenKind.LEVEL_UP_STAT, ScreenKind.ITEM_SOURCE,
                               ScreenKind.DUNGEON_CHOICE, ScreenKind.UNKNOWN}),
    "string": frozenset({ScreenKind.FILE_NAME, ScreenKind.QUANTITY, ScreenKind.UNKNOWN}),
    "any_key": frozenset({ScreenKind.IDENTIFY_VIEWER_PAGE,
                          ScreenKind.IDENTIFY_VIEWER_FINAL, ScreenKind.UNKNOWN}),
    "point": frozenset({ScreenKind.UNKNOWN}),
    # Game develop 92e9029a (tools/bot/README.md "input_context"): the spell
    # list and the birth choices have no screen kind of their own; the file
    # viewer also pages the message log (^P), which the classifier leaves
    # unknown; ``building`` is the building's service menu.
    "spell": frozenset({ScreenKind.UNKNOWN}),
    "building": frozenset({ScreenKind.BUILDING}),
    "file": frozenset({ScreenKind.FILE_VIEWER, ScreenKind.UNKNOWN}),
    "birth": frozenset({ScreenKind.UNKNOWN}),
}


def compatible_kinds(reading: InputContextReading) -> frozenset[ScreenKind]:
    """Screen kinds the published context admits; empty when it says nothing."""
    if reading.source != "server" or reading.kind is None:
        return frozenset()
    if reading.kind == "command":
        return frozenset({ScreenKind.STORE if reading.details.get("shopping") is True
                          else ScreenKind.COMMAND})
    return _COMPATIBLE_KINDS.get(reading.kind, frozenset())


@dataclass(frozen=True)
class InputStateMatch:
    """What the game waits for: the classifier's match plus the context."""

    match: ScreenMatch
    reading: InputContextReading
    state_reading: InputContextReading | None
    verdict: Literal["agree", "disagree", "no-context", "death"]


def current_input_state(screen: Mapping[str, object],
                        state: Mapping[str, object] | None = None) -> InputStateMatch:
    """Answer "which input does the game wait for now" (slice S0).

    ``match`` is exactly ``classify_screen(screen, state)``: S0 takes no
    decision from the context.  The screen reply's context is compared with
    it; the state reply's context is kept for the screen/state agreement.
    """
    match = classify_screen(screen, state)
    reading = read_input_context(screen)
    state_reading = read_input_context(state) if state is not None else None
    if match.kind is ScreenKind.DEATH:
        verdict = "death"
    elif reading.source != "server":
        verdict = "no-context"
    else:
        verdict = "agree" if match.kind in compatible_kinds(reading) else "disagree"
    return InputStateMatch(match, reading, state_reading, verdict)


def stop_line_fields(reading: InputContextReading) -> str:
    """``ctx=<kind|null|absent|unavailable> ctx_prompt=<JSON string>``."""
    prompt = reading.prompt if reading.source == "server" else ""
    return (f"ctx={reading.label} "
            f"ctx_prompt={json.dumps(prompt, ensure_ascii=False)}")


def _screen_row0(screen: object) -> str:
    lines = screen.get("lines") if isinstance(screen, Mapping) else None
    if isinstance(lines, (list, tuple)) and lines:
        return str(lines[0]).rstrip()
    return ""


class InputContextShadow:
    """Agreement counters and the disagreement log (design sections 6.3, 8).

    In memory: per published kind the agreements and disagreements, per source
    the classifications without a context, and per owner the operations whose
    command/store barrier still held continuations (with the context kind).
    On disk (only when ``path`` is set): one line per disagreement, per
    screen/state context mismatch and per residual tail, and a ``counts`` line
    at every stop.  Every write failure is swallowed: recording never changes
    what the bot does.
    """

    def __init__(self, path: Path | None = None,
                 rotate_bytes: int = INPUT_CONTEXT_SHADOW_ROTATE_BYTES) -> None:
        self.path = path
        self.rotate_bytes = rotate_bytes
        self.agreements: dict[str, int] = {}
        self.disagreements: dict[str, int] = {}
        self.without_context: dict[str, int] = {}
        self.residual_continuations: dict[str, dict[str, int]] = {}
        self.write_failures = 0

    @staticmethod
    def _bump(table: dict[str, int], key: str) -> None:
        table[key] = table.get(key, 0) + 1

    def counts(self) -> dict[str, object]:
        return {
            "agree": dict(self.agreements),
            "disagree": dict(self.disagreements),
            "no_context": dict(self.without_context),
            "residual_continuations": {
                owner: dict(kinds) for owner, kinds in self.residual_continuations.items()
            },
        }

    def observe(self, owner: str | None, observed: InputStateMatch,
                screen: Mapping[str, object], *, screen_only: bool) -> None:
        """Count one classification; the state-bound re-classification of the
        same screen only checks the screen/state context agreement."""
        reading = observed.reading
        if not screen_only:
            other = observed.state_reading
            if other is not None and other.source in {"server", "null"} \
                    and reading.source in {"server", "null"} \
                    and (other.source, other.kind, other.prompt) != (
                        reading.source, reading.kind, reading.prompt):
                self._write({"event": "screen-state-mismatch", "owner": owner,
                             "screen_context": reading.as_dict(),
                             "state_context": other.as_dict()})
            return
        if observed.verdict == "agree":
            self._bump(self.agreements, str(reading.kind))
        elif observed.verdict == "disagree":
            self._bump(self.disagreements, str(reading.kind))
            self._write({
                "event": "disagree", "owner": owner,
                "context": reading.as_dict(),
                "heuristic": {"kind": observed.match.kind.value,
                              "feature": observed.match.feature},
                "row0": _screen_row0(screen),
            })
        elif observed.verdict == "no-context":
            self._bump(self.without_context, reading.source)

    def residual(self, owner: str, screen: Mapping[str, object]) -> None:
        """A command/store barrier still holds this operation's continuations."""
        reading = read_input_context(screen)
        kinds = self.residual_continuations.setdefault(owner, {})
        self._bump(kinds, reading.label)
        self._write({"event": "residual-continuations", "owner": owner,
                     "context": reading.as_dict(), "row0": _screen_row0(screen)})

    def stop(self, line: str) -> None:
        self._write({"event": "counts", "stop": line, "counts": self.counts()})

    def _write(self, row: dict[str, object]) -> None:
        if self.path is None:
            return
        record = {"time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                  "pid": os.getpid(), **row}
        try:
            rotate_log(self.path, self.rotate_bytes, 1)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
        except (OSError, TypeError, ValueError):
            self.write_failures += 1
