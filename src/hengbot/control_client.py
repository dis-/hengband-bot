"""Bounded read-only client for Hengband's game-control shadow protocol.

Phase 1 deliberately exposes only ``info`` and ``state`` observations.  All
other operations, including ``screen``, ``messages``, ``keys``, and ``quit``,
are rejected before a request can be composed, so this module cannot control
or terminate the game.
"""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Callable, Mapping

from hengbot.flight_recorder import (
    DEFAULT_LOG_GENERATIONS,
    DEFAULT_LOG_ROTATE_BYTES,
    rotate_log,
)


class ControlClientError(RuntimeError):
    """The control server did not produce a valid response in budget."""


class ControlClient:
    """Persistent newline-JSON connection with bounded reconnect attempts."""

    _READ_ONLY_OPS = frozenset({"info", "state"})

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

    @property
    def connected(self) -> bool:
        return self._socket is not None

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
        if op not in self._READ_ONLY_OPS:
            raise ValueError(f"control operation is forbidden in shadow mode: {op}")
        if self._socket is None:
            self._connect(deadline)
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
            self._buffer.extend(chunk)
        line, _, remainder = self._buffer.partition(b"\n")
        self._buffer = bytearray(remainder)
        response = json.loads(line.decode("utf-8"))
        if not isinstance(response, dict) or response.get("id") != request_id:
            raise ControlClientError("control response id mismatch")
        if response.get("ok") is not True:
            raise ControlClientError(str(response.get("error", "control request failed")))
        result = response.get("result")
        if not isinstance(result, dict):
            raise ControlClientError("control response result is not an object")
        self._failure_visible = False
        self._consecutive_failures = 0
        return result

    def request(
        self, op: str, *, deadline: float | None = None, **fields: object
    ) -> dict | None:
        """Return one observation, or None after bounded reconnect attempts."""
        if op not in self._READ_ONLY_OPS:
            raise ValueError(f"control operation is forbidden in shadow mode: {op}")
        deadline = (
            time.monotonic() + self.request_budget if deadline is None else deadline
        )
        if self._socket is None and time.monotonic() < self._retry_after:
            return None
        last_error: BaseException | None = None
        for _attempt in range(self.retries + 1):
            try:
                return self._request_once(op, fields, deadline)
            except (
                OSError,
                ValueError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                ControlClientError,
            ) as error:
                last_error = error
                self.close()
                if time.monotonic() >= deadline:
                    break
        assert last_error is not None
        self._consecutive_failures += 1
        backoff = min(
            self.backoff * self._consecutive_failures,
            self.request_budget * (self.retries + 1),
        )
        self._retry_after = time.monotonic() + backoff
        self._report_failure_once(last_error)
        return None


def _normalized(value: object) -> object:
    """Remove the map payload intentionally omitted by ``state(map:false)``."""
    if isinstance(value, dict):
        return {
            key: _normalized(child)
            for key, child in value.items()
            if key != "nearby_grids"
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
