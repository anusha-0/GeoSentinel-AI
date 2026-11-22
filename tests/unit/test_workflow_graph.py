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
RESOLVED = {
    "STEP-001": {
        "input_features": "GS_Test_Settlements"
    }
}


def test_missing_input_pauses_for_resolution():
    engine = GeoSentinelWorkflowEngine()
    thread_id = str(uuid.uuid4())

    result = engine.invoke(REQUEST, thread_id)

    assert result["overall_status"] == "INPUT_REQUIRED"
    assert result["input_resolution_status"] == "INCOMPLETE"
    assert "STEP-001.input_features" in result["missing_inputs"]
    assert "execution_payload" not in result

    snapshot = engine.graph.get_state({"configurable": {"thread_id": thread_id}})
    assert snapshot.interrupts
    assert snapshot.interrupts[0].value["event"] == "GEOSENTINEL_INPUT_REQUIRED"
    print("PASS: Missing GIS input pauses at the input-resolution interrupt.")


def test_resolve_inputs_then_pause_for_approval():
    engine = GeoSentinelWorkflowEngine()
    thread_id = str(uuid.uuid4())

    first = engine.invoke(REQUEST, thread_id)
    assert first["overall_status"] == "INPUT_REQUIRED"

    resolved = engine.resolve_inputs(thread_id, RESOLVED)
    assert resolved["input_resolution_status"] == "COMPLETE"
    assert resolved["workflow"]["steps"][0]["inputs"]["input_features"] == "GS_Test_Settlements"

    snapshot = engine.graph.get_state({"configurable": {"thread_id": thread_id}})
    assert snapshot.interrupts
    assert snapshot.interrupts[0].value["event"] == "GEOSENTINEL_APPROVAL_REQUIRED"
    assert "execution_payload" not in resolved
    print("PASS: Input resolution resumes the same workflow and reaches approval.")


def test_approval_interrupt_and_resume():
    engine = GeoSentinelWorkflowEngine()
    thread_id = str(uuid.uuid4())

    engine.invoke(REQUEST, thread_id, resolved_inputs=RESOLVED)
    snapshot = engine.graph.get_state({"configurable": {"thread_id": thread_id}})
    assert snapshot.interrupts
    assert snapshot.interrupts[0].value["event"] == "GEOSENTINEL_APPROVAL_REQUIRED"

    result = engine.resume(thread_id, approved=True)
    assert result["approval_status"] == "APPROVED"
    assert result["overall_status"] == "AWAITING_ARCGIS_PRO"
    assert result["execution_payload"]["approval_status"] == "APPROVED"
    assert "No GIS operation has been executed yet." in result["messages"]
    print("PASS: Approved workflow reaches the ArcGIS Pro handoff without executing GIS.")


def test_rejected_workflow_cannot_reach_execution():
    engine = GeoSentinelWorkflowEngine()
    thread_id = str(uuid.uuid4())

    engine.invoke(REQUEST, thread_id, resolved_inputs=RESOLVED)
    result = engine.resume(thread_id, approved=False)

    assert result["approval_status"] == "REJECTED"
    assert result["overall_status"] == "REJECTED"
    assert "execution_payload" not in result
    print("PASS: Rejected workflow cannot reach execution.")


def test_invalid_input_resolution_is_rejected():
    engine = GeoSentinelWorkflowEngine()
    thread_id = str(uuid.uuid4())
    engine.invoke(REQUEST, thread_id)

    try:
        engine.resolve_inputs(thread_id, {"STEP-999": {"input_features": "x"}})
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown step ID should be rejected.")
    print("PASS: Unknown workflow step IDs are rejected.")


if __name__ == "__main__":
    test_missing_input_pauses_for_resolution()
    test_resolve_inputs_then_pause_for_approval()
    test_approval_interrupt_and_resume()
    test_rejected_workflow_cannot_reach_execution()
    test_invalid_input_resolution_is_rejected()
    print("\nALL GEOSENTINEL WORKFLOW TESTS PASSED.")
