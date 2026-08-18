"""Fast self-tests for the generated verification gates."""

from __future__ import annotations

import unittest

import hunk_guard
import verify_scope


class VerificationGateSelfTest(unittest.TestCase):
    def test_docstringed_failure_id_is_captured(self) -> None:
        output = (
            "test_missing_capture (test_shop_one_shot.ShopTest.test_missing_capture)\n"
            "the displayed test docstring\n"
            " ... FAIL\n"
        )
        self.assertEqual(
            verify_scope.parse_test_failures(output),
            ["test_shop_one_shot.ShopTest.test_missing_capture"],
        )

    def test_dead_known_failure_does_not_match(self) -> None:
        output = "test_x (test_home_knowledge_scan.ScanTest.test_x) ... FAIL\n"
        ids = verify_scope.parse_test_failures(output)
        self.assertEqual(verify_scope.known_failure_matches("tests.test_home_knowledge_scan", output, ids), [])

    def test_known_failure_requires_exactly_one_failure(self) -> None:
        output = "stalled_capture\n"
        self.assertEqual(
            verify_scope.known_failure_matches("tests.test_home_knowledge_scan", output, ["one", "two"]),
            [],
        )

    def test_trailing_comment_is_ast_equivalent(self) -> None:
        body = ["-value = call()  # old\n", "+value = call()  # new\n"]
        self.assertEqual(hunk_guard.classify(body), "nonbehavioral-ast-equivalent")

    def test_new_file_is_marked_by_diff_parser(self) -> None:
        diff = "diff --git a/src/hengbot/new.py b/src/hengbot/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/src/hengbot/new.py\n@@ -0,0 +1 @@\n+x = 1\n"
        self.assertTrue(hunk_guard.parse_hunks(diff)[0]["new_file"])

    def test_reviewed_fake_pin_is_ineligible(self) -> None:
        self.assertIn(
            "test_cli.UniversalPostingContractTest.test_autodestroy_repost_requires_position_effect",
            hunk_guard.INELIGIBLE_PROTECTORS,
        )


if __name__ == "__main__":
    unittest.main()
