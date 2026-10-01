"""Declared wall: the character calibration available when a fixture was extracted.

Recorded replays freeze the extraction-time calibration record by writing it to
the policy's calibration path.  Under the equipped C-sheet calibration rework a
live process loads only its own session's equipped (schema 2) observation from
disk; a historical strip record (schema 1) is no longer read from the file.
These replays therefore also install the frozen record as the policy's
in-memory calibration, which is what the recorded process held at that time.
The record is the recorded fixture itself; nothing is synthesized.
"""
from hengbot.warrior_optimization import load_character_calibration


def install_extraction_calibration(policy):
    """Hold the frozen calibration file's record in memory, as recorded."""
    calibration = load_character_calibration(policy._character_calibration_path)
    if calibration is None:
        raise AssertionError("frozen extraction calibration is unreadable")
    policy._character_calibration = calibration
    policy._character_calibration_loaded = True
    return calibration
