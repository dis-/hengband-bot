"""Explicit skips for recorded pins whose live substrate was evicted."""

import unittest


def needs_fresh_live_capture(scene):
    """Skip a pin until its named scene is captured and frozen."""
    return unittest.skip(f"needs fresh live capture: {scene}")
