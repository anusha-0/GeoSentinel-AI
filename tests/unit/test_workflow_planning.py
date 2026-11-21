import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.planning_agent import GISPlanningAgent
from agents.workflow_validator import WorkflowValidator


def main():

    agent = GISPlanningAgent()
    validator = WorkflowValidator()

    request = (
        "Create a 500-meter buffer around settlements "
        "and dissolve overlapping buffers."
    )

    workflow = agent.plan(request)

    workflow_dict = workflow.model_dump(mode="json")

    print("\n========== GEOSENTINEL WORKFLOW PLAN ==========\n")

    print(workflow.model_dump_json(indent=4))

    print("\n========== WORKFLOW VALIDATION ==========\n")

    result = validator.validate(workflow_dict)

    print(result)

    assert workflow.workflow_id.startswith("GS-WF-")
    assert workflow.steps[0].operation_id == "buffer"
    assert workflow.steps[0].parameters["distance"] == "500 Meters"
    assert workflow.steps[0].parameters["dissolve_option"] == "ALL"

    # Validation should fail because input layer is not selected yet.
    assert result["valid"] is False
    assert any(
    "requires user selection" in error
    for error in result["errors"]
)

    print("\nTEST PASSED: Planner generated the expected workflow.")
    print("Expected validation failure: input layer requires selection.")


if __name__ == "__main__":
    main()