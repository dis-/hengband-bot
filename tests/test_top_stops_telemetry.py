"""Short recorded tour prefix for the completion-receipt purity regression."""
import tests  # noqa: F401
import unittest
import tests.test_pure_decision_telemetry as telemetry


class TopStopsTelemetryTest(unittest.TestCase):
    @telemetry.pre_light_radius_replay
    @telemetry.recorded_loadout_replay
    def test_recorded_tour_completion_receipt_does_not_depend_on_diagnostic_polls(self):
        # The unmodified recorded fixture's first two decision boundaries
        # include the first observed completion. One policy polls telemetry
        # after every decision; the independent control never polls it.
        lockstep, _ = telemetry.PureDecisionTelemetryTest._recorded_lifetime(
            self, telemetry.tour.FIXTURE, telemetry.tour.FIXTURE_SHA256,
            telemetry._tour_build, telemetry._tour_walls, 2)
        lockstep.assert_pure()
