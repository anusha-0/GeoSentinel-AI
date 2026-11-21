import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestration.workflow_graph import GeoSentinelWorkflowEngine


REQUEST = (
    "Create a 500-meter buffer around settlements "
    "and dissolve overlapping buffers."
)


def test_missing_input_stops_workflow():

    engine = GeoSentinelWorkflowEngine()

    result = engine.invoke(
        user_request=REQUEST,
        thread_id=str(uuid.uuid4())
    )

    assert result["overall_status"] == "INPUT_REQUIRED"

    assert "STEP-001.input_features" in result["missing_inputs"]

    assert "execution_payload" not in result

    print("PASS: Missing input blocks workflow execution.")


def test_approval_interrupt_and_resume():

    engine = GeoSentinelWorkflowEngine()

    thread_id = str(uuid.uuid4())

    result = engine.invoke(
        user_request=REQUEST,
        thread_id=thread_id,
        resolved_inputs={
            "STEP-001": {
                "input_features": "GS_Test_Settlements"
            }
        }
    )

    snapshot = engine.graph.get_state(
        {
            "configurable": {
                "thread_id": thread_id
            }
        }
    )

    assert snapshot.interrupts, "Expected approval interrupt."

    print("PASS: Workflow paused for human approval.")

    result = engine.resume(
        thread_id=thread_id,
        approved=True
    )

    assert result["approval_status"] == "APPROVED"

    assert result["overall_status"] == "AWAITING_ARCGIS_PRO"

    assert result["execution_payload"]["approval_status"] == "APPROVED"

    print("PASS: Approved workflow reached execution handoff.")

    assert "No GIS operation has been executed yet." in result["messages"]


def test_rejected_workflow():

    engine = GeoSentinelWorkflowEngine()

    thread_id = str(uuid.uuid4())

    engine.invoke(
        user_request=REQUEST,
        thread_id=thread_id,
        resolved_inputs={
            "STEP-001": {
                "input_features": "GS_Test_Settlements"
            }
        }
    )

    result = engine.resume(
        thread_id=thread_id,
        approved=False
    )

    assert result["approval_status"] == "REJECTED"

    assert result["overall_status"] == "REJECTED"

    assert "execution_payload" not in result

    print("PASS: Rejected workflow cannot reach execution.")


if __name__ == "__main__":

    test_missing_input_stops_workflow()

    test_approval_interrupt_and_resume()

    test_rejected_workflow()

    print("\nALL GEOSENTINEL WORKFLOW TESTS PASSED.")