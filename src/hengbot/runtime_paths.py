"""Locations of the bot's durable runtime files, overridable for isolation.

Production leaves ``HENGBOT_RUNTIME_DIR`` unset, so every default below stays
``jsonlog/...`` relative to the working directory exactly as before.  Test
sessions and test runners set it (and ``HENGBOT_HOME_HISTORY_DIR``) to
temporary directories so neither a fresh CLI run nor a restored live
checkpoint can write the running bot's files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hengbot.home_disposal import HOME_HISTORY_DIR_ENV


RUNTIME_DIR_ENV = "HENGBOT_RUNTIME_DIR"
DEFAULT_RUNTIME_DIR = Path("jsonlog")
# Policy attributes that name a durable file the policy itself writes.  The
# CLI points them beside the decision log (jsonlog/ in production), so a
# checkpoint captured from the live bot carries those live locations.
POLICY_RUNTIME_PATH_ATTRIBUTES = (
    "_confirmed_loadout_path",
    "_loadout_report_path",
    "_character_calibration_path",
    "_latch_capture_path",
)


def configured_runtime_dir() -> Path | None:
    value = os.environ.get(RUNTIME_DIR_ENV, "").strip()
    return Path(value) if value else None


def runtime_dir() -> Path:
    """Directory for runtime files; ``jsonlog`` unless overridden."""
    return configured_runtime_dir() or DEFAULT_RUNTIME_DIR


def runtime_path(name: str) -> Path:
    return runtime_dir() / name


def configured_home_history_dir() -> Path | None:
    value = os.environ.get(HOME_HISTORY_DIR_ENV, "").strip()
    return Path(value) if value else None


def isolate_restored_runtime_paths(policy: Any) -> None:
    """Re-point a restored policy's stored file paths at the configured overrides.

    A no-op when neither override is set, which is the production case, so a
    live bot's disposable checkpoint clones keep their exact behaviour.
    """
    state = policy.__dict__
    runtime = configured_runtime_dir()
    if runtime is not None:
        for name in POLICY_RUNTIME_PATH_ATTRIBUTES:
            value = state.get(name)
            if value is not None:
                state[name] = runtime / Path(value).name
        ledger = state.get("_exploration_ledger")
        if ledger is not None and getattr(ledger, "path", None) is not None:
            ledger.path = runtime / Path(ledger.path).name
    home_root = configured_home_history_dir()
    home = state.get("_home_disposal")
    if home_root is not None and home is not None:
        home.relocate(home_root)
