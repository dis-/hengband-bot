"""Controls for sampled merge checks and the daily full-module inventory."""

import ast
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import gate_sample
from scripts import purity_cache


class GateSampleTest(unittest.TestCase):
    def test_default_and_one_return_original_list(self):
        items = [object(), object()]
        with patch.dict(os.environ):
            os.environ.pop(gate_sample.SAMPLE_ENV, None)
            self.assertIs(gate_sample.sample(items), items)
            os.environ[gate_sample.SAMPLE_ENV] = "1"
            self.assertIs(gate_sample.sample(items), items)

    def test_stride_keeps_endpoints_order_and_does_not_mutate(self):
        items = list(range(13))
        with patch.dict(os.environ, {gate_sample.SAMPLE_ENV: "5"}):
            self.assertEqual(gate_sample.sample(items), [0, 5, 10, 12])
            self.assertEqual(gate_sample.sample(items[:11]), [0, 5, 10])
            self.assertEqual(gate_sample.sample(items[:2]), [0, 1])
            self.assertEqual(gate_sample.sample(items[:1]), [0])
            self.assertEqual(gate_sample.sample([]), [])
            self.assertEqual(gate_sample.sample(items), gate_sample.sample(items))
        self.assertEqual(items, list(range(13)))

    def test_equal_values_keep_positional_endpoints(self):
        first, last = [1], [1]
        with patch.dict(os.environ, {gate_sample.SAMPLE_ENV: "5"}):
            selected = gate_sample.sample([first, last])
        self.assertIs(selected[0], first)
        self.assertIs(selected[-1], last)
        self.assertEqual(len(selected), 2)

    def test_bad_values_fail_even_for_empty_input(self):
        for value in ("", "0", "-1", "1.5", "abc"):
            with self.subTest(value=value), patch.dict(
                os.environ, {gate_sample.SAMPLE_ENV: value}
            ):
                with self.assertRaisesRegex(ValueError, gate_sample.SAMPLE_ENV):
                    gate_sample.sample([])

    def test_sampled_pass_cannot_satisfy_full_purity_cache(self):
        root = Path(__file__).resolve().parents[1]
        with patch.object(purity_cache, "dependency_files", return_value=()):
            with patch.dict(os.environ):
                os.environ.pop(gate_sample.SAMPLE_ENV, None)
                full, _ = purity_cache.input_sha256(root)
                os.environ[gate_sample.SAMPLE_ENV] = "1"
                explicit_full, _ = purity_cache.input_sha256(root)
                os.environ[gate_sample.SAMPLE_ENV] = "5"
                sampled, _ = purity_cache.input_sha256(root)
        self.assertEqual(full, explicit_full)
        self.assertNotEqual(full, sampled)

    def test_purity_cache_tracks_sampler_implementation(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn(root / "tests" / "gate_sample.py", purity_cache.dependency_files(root))

    def test_daily_inventory_matches_sampling_test_modules(self):
        root = Path(__file__).parent
        importing = set()
        for path in root.glob("test_*.py"):
            if path.name == "test_gate_sample.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (
                    node.module == "tests.gate_sample"
                    or node.module == "tests" and any(
                        alias.name == "gate_sample" for alias in node.names
                    )
                ) or isinstance(node, ast.Import) and any(
                    alias.name == "tests.gate_sample" for alias in node.names
                ):
                    importing.add(f"tests.{path.stem}")
        self.assertEqual(len(gate_sample.SAMPLED_MODULES), len(set(gate_sample.SAMPLED_MODULES)))
        self.assertEqual(set(gate_sample.SAMPLED_MODULES), importing)
