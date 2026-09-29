"""Record-only execution declarations survive checkpoints and claim transitions."""

import pickle
import unittest

from hengbot.claim_register import ClaimRegister, reach


class ExecutionDeclarationTest(unittest.TestCase):
    def test_revision_and_checkpoint_round_trip(self):
        register = ClaimRegister()
        claim = register.declare("store-router", reach((31, 150)))
        first = register.declare_execution(
            claim.claim_id, work_id="route:entrance:31,150",
            producer="store-router", state="acting", next_step="route.resume",
            arguments=("entrance", (31, 150)), budget_ref="town-travel",
        )
        self.assertEqual(first.revision, 1)
        restored = pickle.loads(pickle.dumps(register))
        self.assertEqual(restored.current.execution, first)
        restored.await_observation()
        self.assertEqual(restored.current.execution, first)
        second = restored.declare_execution(
            claim.claim_id, work_id=first.work_id, producer="store-router",
            state="awaiting", operation_ref="decision:223:travel",
            expected_effect="arrive:31,150", continuation="route.resume",
        )
        self.assertEqual(second.revision, 2)
        self.assertEqual(restored.current.as_dict()["execution"]["state"],
                         "awaiting")
        self.assertIsNone(restored.declare_execution(
            claim.claim_id + 1, work_id="wrong", producer="store-router",
            state="acting", next_step="route.resume"))

    def test_predeclaration_checkpoint_reads_class_default(self):
        register = ClaimRegister()
        claim = register.declare("store-router", reach((31, 150)))
        del claim.__dict__["execution"]
        restored = pickle.loads(pickle.dumps(register))
        self.assertIsNone(restored.current.execution)
        self.assertIsNone(restored.current.as_dict()["execution"])


if __name__ == "__main__":
    unittest.main()
