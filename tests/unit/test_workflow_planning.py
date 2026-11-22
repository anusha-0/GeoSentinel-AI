import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.planning_agent import GISPlanningAgent
from agents.workflow_validator import WorkflowValidator


REQUEST = (
    "Create a 500-meter buffer around settlements "
    "and dissolve overlapping buffers."
)


def test_planner_generates_expected_buffer_workflow():

    agent = GISPlanningAgent()

    workflow = agent.plan(REQUEST)

    assert workflow.workflow_id.startswith("GS-WF-")
    assert workflow.steps[0].operation_id == "buffer"
    assert workflow.steps[0].parameters["distance"] == "500 Meters"
    assert workflow.steps[0].parameters["dissolve_option"] == "ALL"


def test_unresolved_input_fails_workflow_validation():

    agent = GISPlanningAgent()
    validator = WorkflowValidator()

    workflow = agent.plan(REQUEST)
    workflow_dict = workflow.model_dump(mode="json")

    result = validator.validate(workflow_dict)

    assert result["valid"] is False

    assert any(
        "requires user selection" in error
        for error in result["errors"]
    )