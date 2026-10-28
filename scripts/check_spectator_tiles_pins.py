"""Behavioural per-pin mutations in a disposable source copy; checkout stays intact."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PIN = "tests.test_spectator_tiles.SpectatorTilesTest."
MUTANTS = [
    ("derive", "spectator_tiles.py", 'return derived, "derived"', 'return None, "derived"',
     PIN + "test_missing_panel_is_derived_from_this_screen"),
    ("zero", "spectator_tiles.py", 'return None, "player_glyph_count"',
     'return state.get("panel"), "player_glyph_count"',
     PIN + "test_zero_or_two_map_anchors_omit_even_with_a_state_panel"),
    ("two", "spectator_tiles.py", 'len(anchors) != 1', 'not anchors',
     PIN + "test_zero_or_two_map_anchors_omit_even_with_a_state_panel"),
    ("row_offset", "spectator_tiles.py", '(row - ROW_MAP)', 'row',
     PIN + "test_missing_panel_is_derived_from_this_screen"),
    ("col_offset", "spectator_tiles.py", '(col - COL_MAP)', 'col',
     PIN + "test_missing_panel_is_derived_from_this_screen"),
    ("row_clip", "spectator_tiles.py", 'if row >= ROW_MAP', 'if True',
     PIN + "test_anchor_search_is_clipped_to_the_map_area"),
    ("bottom_clip", "spectator_tiles.py", '[:screen["height"] - 1]', '[:]',
     PIN + "test_anchor_search_is_clipped_to_the_map_area"),
    ("col_clip", "spectator_tiles.py", 'line[COL_MAP:screen["width"]]', 'line[:screen["width"]]',
     PIN + "test_anchor_search_is_clipped_to_the_map_area"),
    ("right_clip", "spectator_tiles.py", 'line[COL_MAP:screen["width"]]', 'line[COL_MAP:]',
     PIN + "test_anchor_search_is_clipped_to_the_map_area"),
    ("panel_agreement", "spectator_tiles.py", 'panel[key] != value', 'False',
     PIN + "test_state_panel_must_agree_with_both_derived_coordinates"),
    ("counts", "spectator_tiles.py", 'panel_counts[outcome] = panel_counts.get(outcome, 0) + 1', 'pass',
     PIN + "test_state_panel_must_agree_with_both_derived_coordinates"),
    ("position", "spectator_tiles.py", 'return None, "player_position"', 'return state.get("panel"), "player_position"',
     PIN + "test_missing_player_position_does_not_invent_an_origin"),
    ("writer_counts", "spectator.py", 'panel_counts=self.tile_panel_counts', 'panel_counts=None',
     "tests.test_spectator_tiles.SpectatorTilesWriterTest.test_snapshot_and_deferred_frame_use_the_same_received_state"),
]


def main():
    with TemporaryDirectory(prefix="spectate-tiles-pins-") as directory:
        copied = Path(directory) / "hengbot"
        shutil.copytree(ROOT / "src/hengbot", copied, ignore=shutil.ignore_patterns("__pycache__"))
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((directory, str(ROOT / "tests"), str(ROOT / "scripts"))),
                   PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        def run(pin):
            return subprocess.run([sys.executable, "-m", "unittest", pin], cwd=ROOT, env=env,
                                  capture_output=True, text=True, encoding="utf-8", timeout=120)
        baseline = run("tests.test_spectator_tiles")
        if baseline.returncode:
            raise RuntimeError(baseline.stderr)
        for label, name, before, after, pin in MUTANTS:
            path = copied / name
            original = path.read_text(encoding="utf-8")
            assert original.count(before) == 1, label
            path.write_text(original.replace(before, after), encoding="utf-8", newline="\n")
            try:
                result = run(pin)
                # Require an assertion failure; import/schema errors do not prove behaviour.
                if result.returncode != 1 or "FAIL:" not in result.stderr or "ERROR:" in result.stderr:
                    raise RuntimeError(f"not caught: {label}\n{result.stderr}")
                print(f"caught {label}: {pin}", flush=True)
            finally:
                path.write_text(original, encoding="utf-8", newline="\n")
    print(f"caught {len(MUTANTS)}/{len(MUTANTS)}")


if __name__ == "__main__":
    main()
