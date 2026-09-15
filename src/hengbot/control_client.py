"""Bounded client for Hengband's observation and controlled-key protocol."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping

from hengbot.flight_recorder import (
    DEFAULT_LOG_GENERATIONS,
    DEFAULT_LOG_ROTATE_BYTES,
    rotate_log,
)


class ControlClientError(RuntimeError):
    """The control server did not produce a valid response in budget."""


class ControlServerError(ControlClientError):
    """The server rejected a well-formed request."""


class KeyPostStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NOT_ATTEMPTED = "not-attempted"
    ACCEPTANCE_UNKNOWN = "acceptance-unknown"


@dataclass(frozen=True)
class KeyPostOutcome:
    status: KeyPostStatus
    request_id: int | None = None
    accepted_count: int | None = None
    reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status is KeyPostStatus.ACCEPTED


class ControlClient:
    """Persistent newline-JSON connection with bounded reconnect attempts."""

    _READ_ONLY_OPS = frozenset({"info", "state", "screen"})
    _ALLOWED_OPS = _READ_ONLY_OPS | {"keys"}
    BACKPRESSURE_ERROR = "the key queue does not have enough room"

    def __init__(
        self,
        port: int,
        *,
        request_budget: float,
        retries: int = 1,
        backoff: float | None = None,
        log: Callable[[str], None] | None = None,
        socket_factory: Callable[..., socket.socket] = socket.create_connection,
    ) -> None:
        self.port = port
        self.request_budget = request_budget
        self.retries = retries
        self.backoff = request_budget if backoff is None else backoff
        self._log = log or (lambda _message: None)
        self._socket_factory = socket_factory
        self._socket: socket.socket | None = None
        self._buffer = bytearray()
        self._next_id = 1
        self._retry_after = 0.0
        self._consecutive_failures = 0
        self._failure_visible = False
        # Changes whenever a read-only request discards its connection and
        # retries.  Barrier users use this to invalidate a prior screen/state
        # pair rather than combining observations across reconnects.
        self._observation_epoch = 0
        self.last_error: str | None = None
        self.backpressured = False
        self._request_timings: list[dict[str, object]] = []
        self._current_attempt = 1
        self._timing_request_id = 0
        self._timing_connected = False
        self._timing_started_at: float | None = None
        self._collect_request_timings = False

    def start_request_timings(self) -> None:
        self._request_timings = []
        self._collect_request_timings = True

    def take_request_timings(self) -> list[dict[str, object]]:
        """Return and clear observational timings collected since the last take."""
        timings = self._request_timings
        self._request_timings = []
        self._collect_request_timings = False
        return timings

    @property
    def connected(self) -> bool:
        return self._socket is not None

    @property
    def observation_epoch(self) -> int:
        return self._observation_epoch

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None
                self._buffer.clear()

    def _report_failure_once(self, error: BaseException) -> None:
        if not self._failure_visible:
            self._log(f"tcp-shadow unavailable: {error}")
            self._failure_visible = True

    def _connect(self, deadline: float) -> None:
        now = time.monotonic()
        if now < self._retry_after:
            raise ControlClientError("reconnect backoff is active")
        remaining = deadline - now
        if remaining <= 0:
            raise TimeoutError("control request budget exhausted")
        connection = self._socket_factory(
            ("127.0.0.1", self.port), timeout=remaining
        )
        connection.settimeout(remaining)
        self._socket = connection
        self._buffer.clear()

    def _request_once(self, op: str, fields: Mapping[str, object], deadline: float) -> dict:
        before = len(self._request_timings)
        started = time.perf_counter()
        try:
            return self._perform_request_once(op, fields, deadline)
        except BaseException:
            self._timing_connected = False
            self._timing_started_at = None
            if self._collect_request_timings and len(self._request_timings) == before:
                self._request_timings.append({
                    "kind": op,
                    "request_first_byte_ms": round(
                        (time.perf_counter() - started) * 1000, 3),
                    "first_last_byte_ms": 0.0,
                    "json_decode_ms": 0.0,
                    "response_bytes": 0,
                    "connected": self._socket is None,
                    "attempt": self._current_attempt,
                    "retry_count": self._current_attempt - 1,
                    "request": self._timing_request_id,
                })
            raise

    def _perform_request_once(self, op: str, fields: Mapping[str, object], deadline: float) -> dict:
        if op not in self._ALLOWED_OPS:
            raise ValueError(f"control operation is forbidden: {op}")
        connected = self._timing_connected
        started = self._timing_started_at or time.perf_counter()
        self._timing_connected = False
        self._timing_started_at = None
        first_byte_at: float | None = None
        response_bytes = 0
        if self._socket is None:
            self._connect(deadline)
            connected = True
        request_id = self._next_id
        self._next_id += 1
        payload = {"id": request_id, "op": op, **fields}
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("control request budget exhausted")
        assert self._socket is not None
        self._socket.settimeout(remaining)
        self._socket.sendall(
            (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        )
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("control response timed out")
            self._socket.settimeout(remaining)
            chunk = self._socket.recv(65536)
            if not chunk:
                raise ConnectionError("control server disconnected")
            if first_byte_at is None:
                first_byte_at = time.perf_counter()
            response_bytes += len(chunk)
            self._buffer.extend(chunk)
        line, _, remainder = self._buffer.partition(b"\n")
        self._buffer = bytearray(remainder)
        last_byte_at = time.perf_counter()
        decode_started = time.perf_counter()
        response = json.loads(line.decode("utf-8"))
        decoded_at = time.perf_counter()
        if self._collect_request_timings:
            self._request_timings.append({
                "kind": op,
                "request_first_byte_ms": round(
                    ((first_byte_at or last_byte_at) - started) * 1000, 3),
                "first_last_byte_ms": round(
                    (last_byte_at - (first_byte_at or last_byte_at)) * 1000, 3),
                "json_decode_ms": round((decoded_at - decode_started) * 1000, 3),
                "response_bytes": response_bytes,
                "connected": connected,
                "attempt": self._current_attempt,
                "retry_count": self._current_attempt - 1,
                "request": self._timing_request_id,
            })
        if not isinstance(response, dict) or response.get("id") != request_id:
            raise ControlClientError("control response id mismatch")
        if response.get("ok") is not True:
            raise ControlServerError(str(response.get("error", "control request failed")))
        result = response.get("result")
        if not isinstance(result, dict):
            raise ControlClientError("control response result is not an object")
        self._failure_visible = False
        self._consecutive_failures = 0
        return result

    def post_keys(
        self, keys: str, *, expected_count: int | None, deadline: float | None = None
    ) -> KeyPostOutcome:
        """Attempt one mutating request exactly once.

        A request that reached ``sendall`` has unknown acceptance unless its
        matching, exact ACK is received.  In particular, mutation failures are
        never reconnected and replayed.
        """
        self.last_error = None
        self.backpressured = False
        deadline = time.monotonic() + self.request_budget if deadline is None else deadline
        request_id = self._next_id
        if time.monotonic() >= deadline:
            return KeyPostOutcome(KeyPostStatus.NOT_ATTEMPTED, reason="request budget exhausted")
        attempted = False
        try:
            self._timing_request_id += 1
            self._current_attempt = 1
            self._timing_started_at = time.perf_counter()
            self._timing_connected = self._socket is None
            if self._socket is None:
                self._connect(deadline)
            attempted = True
            result = self._request_once("keys", {"keys": keys}, deadline)
        except ControlServerError as error:
            self.last_error = str(error)
            self.backpressured = self.last_error == self.BACKPRESSURE_ERROR
            self.close()
            return KeyPostOutcome(
                KeyPostStatus.REJECTED, request_id=request_id, reason=self.last_error
            )
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError,
                ControlClientError) as error:
            self.last_error = str(error)
            self.close()
            status = (KeyPostStatus.ACCEPTANCE_UNKNOWN if attempted
                      else KeyPostStatus.NOT_ATTEMPTED)
            return KeyPostOutcome(status, request_id=request_id, reason=self.last_error)
        pushed = result.get("pushed")
        if (not isinstance(pushed, int) or isinstance(pushed, bool)
                or (expected_count is not None and pushed != expected_count)):
            self.last_error = f"control keys pushed {pushed!r}, expected {expected_count}"
            self.close()
            return KeyPostOutcome(
                KeyPostStatus.ACCEPTANCE_UNKNOWN, request_id=request_id,
                accepted_count=pushed if isinstance(pushed, int) else None,
                reason=self.last_error,
            )
        return KeyPostOutcome(
            KeyPostStatus.ACCEPTED, request_id=request_id, accepted_count=pushed
        )

    def request(
        self, op: str, *, deadline: float | None = None,
        retry_until_deadline: bool = False, **fields: object
    ) -> dict | None:
        """Return one observation, or None after bounded reconnect attempts."""
        if op not in self._READ_ONLY_OPS:
            raise ValueError(f"control operation is forbidden in shadow mode: {op}")
        deadline = (
            time.monotonic() + self.request_budget if deadline is None else deadline
        )
        if (not retry_until_deadline and self._socket is None
                and time.monotonic() < self._retry_after):
            return None
        last_error: BaseException | None = None
        attempt = 0
        self._timing_request_id += 1
        while retry_until_deadline or attempt < self.retries + 1:
            attempt += 1
            self._current_attempt = attempt
            if time.monotonic() >= deadline:
                last_error = TimeoutError("control request budget exhausted")
                break
            try:
                # The caller's deadline is the granted observation budget.
                # A transport failure that arrives before it may reconnect;
                # a slow valid reply retains the entire remaining budget.
                return self._request_once(op, fields, deadline)
            except (
                OSError,
                ValueError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ControlClientError,
            ) as error:
                last_error = error
                self._observation_epoch += 1
                self.close()
                if time.monotonic() >= deadline:
                    break
        assert last_error is not None
        if op == "screen" and isinstance(last_error, TimeoutError):
            # A screen may legitimately consume its entire caller budget while
            # the game reaches inkey().  Keep ordinary callers eligible to
            # issue their existing visible recovery input immediately.
            self._report_failure_once(last_error)
            return None
        self._consecutive_failures += 1
        backoff = min(
            self.backoff * self._consecutive_failures,
            self.request_budget * (self.retries + 1),
        )
        self._retry_after = time.monotonic() + backoff
        self._report_failure_once(last_error)
        return None

    def send_keys(self, keys: str, *, deadline: float | None = None) -> int | None:
        """Send macro-notation keys and return the acknowledged decoded count.

        Server rejections are exposed through ``last_error``. Backpressure is
        separately identified by ``backpressured`` so callers can wait and
        retry without mistaking it for a broken transport.
        """
        outcome = self.post_keys(
            keys, expected_count=_macro_notation_count(keys), deadline=deadline
        )
        if outcome.status is KeyPostStatus.REJECTED:
            self._log(f"tcp-input rejected: {outcome.reason}")
        elif outcome.status is KeyPostStatus.ACCEPTANCE_UNKNOWN:
            self._report_failure_once(ControlClientError(outcome.reason or outcome.status.value))
        return outcome.accepted_count if outcome.accepted else None


def _macro_notation_count(value: str) -> int:
    """Count bytes in the control server's text_to_ascii notation grammar."""
    count = index = 0
    while index < len(value):
        if value[index] == "\\":
            index += 1
            if index >= len(value):
                raise ValueError("trailing macro escape")
            if value[index] == "x":
                if index + 2 >= len(value):
                    raise ValueError("short hexadecimal macro escape")
                int(value[index + 1:index + 3], 16)
                index += 2
        elif value[index] == "^":
            index += 1
            if index >= len(value):
                raise ValueError("trailing control macro escape")
        count += 1
        index += 1
    return count


def raw_keys_to_macro_notation(keys: str) -> str:
    """Encode an 8-bit raw key string for Hengband's ``text_to_ascii``."""
    encoded: list[str] = []
    escapes = {
        8: r"\b", 9: r"\t", 10: r"\n", 13: r"\r", 27: r"\e",
        32: r"\s", 92: r"\\", 94: r"\^",
    }
    for character in keys:
        value = ord(character)
        if value == 0 or value > 255:
            raise ValueError(f"raw key byte is not safely representable: {value:#x}")
        if value in escapes:
            encoded.append(escapes[value])
        elif value < 32:
            encoded.append("^" + chr(value | 64))
        elif 33 <= value <= 126:
            encoded.append(character)
        else:
            encoded.append(f"\\x{value:02X}")
    return "".join(encoded)


def _normalized(value: object) -> object:
    """Remove the map payload intentionally omitted by ``state(map:false)``."""
    if isinstance(value, dict):
        return {
            key: _normalized(child)
            for key, child in value.items()
            if key not in {"nearby_grids", "grid_map"}
        }
    if isinstance(value, list):
        return [_normalized(child) for child in value]
    return value


def append_shadow_diff(
    client: ControlClient,
    jsonl_state: Mapping[str, object],
    *,
    decision_sequence: int,
    path: Path,
    rotate_bytes: int = DEFAULT_LOG_ROTATE_BYTES,
    generations: int = DEFAULT_LOG_GENERATIONS,
) -> dict | None:
    """Observe TCP state without returning either observation to policy."""
    started = time.perf_counter()
    deadline = time.monotonic() + client.request_budget
    tcp_state = client.request("state", deadline=deadline, map=False)
    if tcp_state is None:
        return None
    tcp = dict(tcp_state)
    left = _normalized(dict(jsonl_state))
    right = _normalized(tcp)
    if not isinstance(left, dict) or not isinstance(right, dict):
        client._report_failure_once(ControlClientError("shadow state is not an object"))
        return None
    # JSONL emits RECENT_DIFF while TCP state carries the 32-entry HISTORY
    # (bot-json-output.cpp:428-455,943-953,1669,1676).  Compare the delta with
    # the equally-sized history tail instead of pretending the windows match.
    left_messages = left.get("messages")
    right_messages = right.get("messages")
    if isinstance(left_messages, list) and isinstance(right_messages, list):
        right["messages"] = right_messages[-len(left_messages):] if left_messages else []
    # Store JSONL snapshots identify their emission site as ``store``; TCP state
    # uses the command-loop snapshot type ``player_turn`` for the same state.
    if left.get("type") == "store" and right.get("type") == "player_turn":
        left["type"] = "player_turn"
    diff_keys = sorted(
        key for key in left.keys() | right.keys() if left.get(key) != right.get(key)
    )
    row = {
        "decision_sequence": decision_sequence,
        "turn_jsonl": left.get("turn"),
        "turn_tcp": right.get("turn"),
        "equal": not diff_keys,
        "diff_keys": diff_keys,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    try:
        rotate_log(path, rotate_bytes, generations)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    except OSError as error:
        client._report_failure_once(error)
        return None
    return row
