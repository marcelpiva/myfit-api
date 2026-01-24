"""
E2E Test Scenarios.

Each scenario is a function that sets up a specific test state in the database
and returns credentials/data needed for external test clients (Playwright, etc).
"""

from tests.e2e.scenarios.cotraining import setup_cotraining_scenario
from tests.e2e.scenarios.plan_assignment import setup_plan_assignment_scenario
from tests.e2e.scenarios.feedback_loop import setup_feedback_loop_scenario

SCENARIOS = {
    "cotraining": setup_cotraining_scenario,
    "plan_assignment": setup_plan_assignment_scenario,
    "feedback_loop": setup_feedback_loop_scenario,
}

__all__ = [
    "SCENARIOS",
    "setup_cotraining_scenario",
    "setup_plan_assignment_scenario",
    "setup_feedback_loop_scenario",
]
