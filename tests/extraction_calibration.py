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


def restore_recorded_checkpoint(policy_type, encoded):
    """Restore a recorded checkpoint with the calibration its process held.

    The checkpoint upgrade drops constants this process did not observe
    (schema-1 or another session).  A recorded capture that is replayed as
    evidence of the recorded process re-injects its own record explicitly.
    """
    import base64
    import io
    import pathlib
    import pickle
    from hengbot.latch_onset_capture import restore_checkpoint

    class _Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            if module == "pathlib._local":
                return getattr(pathlib, name)
            return super().find_class(module, name)

    state = _Unpickler(io.BytesIO(base64.b64decode(encoded))).load()
    policy = restore_checkpoint(policy_type, encoded)
    recorded = state.get("_character_calibration")
    if recorded is not None:
        policy._character_calibration = recorded
        policy._character_calibration_loaded = True
    return policy
