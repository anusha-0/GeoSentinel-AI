import sys
from pathlib import Path

import pytest

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

    workflow = GISPlanningAgent().plan(REQUEST)

    step = workflow.steps[0]

    assert step.operation_id == "buffer"
    assert step.parameters["distance"] == "500 Meters"
    assert step.parameters["dissolve_option"] == "ALL"
    assert step.output_name == "GS_Buffer_Output"
    assert workflow.approval_required is True
    assert workflow.metadata["planner_version"] == "0.3.0"


def test_unresolved_input_fails_workflow_validation():

    workflow = GISPlanningAgent().plan(REQUEST)

    result = WorkflowValidator().validate(
        workflow.model_dump(mode="json")
    )

    assert result["valid"] is False
    assert any(
        "requires user selection" in error
        for error in result["errors"]
    )


@pytest.mark.parametrize(
    "user_request, expected",
    [
        (
            "Use GS_Test_Settlements as input",
            "GS_Test_Settlements"
        ),
        (
            "Input features: GS_Test_Settlements",
            "GS_Test_Settlements"
        ),
        (
            "Use layer GS_Test_Settlements",
            "GS_Test_Settlements"
        ),
        (
            "Use dataset GS_Test_Settlements",
            "GS_Test_Settlements"
        ),
    ]
)
def test_input_name_extraction(user_request, expected):

    assert (
        GISPlanningAgent.extract_input_name(user_request)
        == expected
    )


@pytest.mark.parametrize(
    "user_request, expected",
    [
        (
            "Save as GS_Buffer_Test",
            "GS_Buffer_Test"
        ),
        (
            "Save the output as GS_Buffer_Test",
            "GS_Buffer_Test"
        ),
        (
            "Output name: GS_Buffer_Test",
            "GS_Buffer_Test"
        ),
        (
            "Create output named GS_Buffer_Test",
            "GS_Buffer_Test"
        ),
    ]
)
def test_output_name_extraction(user_request, expected):

    assert (
        GISPlanningAgent.extract_output_name(user_request)
        == expected
    )


def test_combined_input_and_output_extraction():

    request = (
        "Create a 500-meter buffer around settlements "
        "and dissolve overlapping buffers. "
        "Use GS_Test_Settlements as the input "
        "and save the output as GS_Buffer_V095_Test."
    )

    workflow = GISPlanningAgent().plan(request)

    step = workflow.steps[0]

    assert step.inputs["input_features"] == "GS_Test_Settlements"
    assert step.output_name == "GS_Buffer_V095_Test"
    assert step.parameters["distance"] == "500 Meters"
    assert step.parameters["dissolve_option"] == "ALL"


def test_missing_input_retains_interactive_resolution():

    workflow = GISPlanningAgent().plan(REQUEST)

    assert (
        workflow.steps[0].inputs["input_features"]
        == "USER_SELECT_REQUIRED"
    )

    assert workflow.metadata["requires_user_input"] == [
        "input_features"
    ]


def test_missing_output_uses_default():

    assert (
        GISPlanningAgent.extract_output_name(REQUEST)
        == "GS_Buffer_Output"
    )


def test_dataset_name_maximum_length():

    valid_name = "A" + ("B" * 63)

    assert (
        GISPlanningAgent._validate_dataset_name(valid_name)
        == valid_name
    )


@pytest.mark.parametrize(
    "invalid_name",
    [
        "9Invalid",
        "Invalid-Name",
        "Invalid Name",
        "A" * 65,
    ]
)
def test_invalid_dataset_names_are_rejected(invalid_name):

    with pytest.raises(ValueError):
        GISPlanningAgent._validate_dataset_name(invalid_name)


def test_explicit_input_and_output_workflow_validates():

    request = (
        "Create a 500-meter buffer. "
        "Use GS_Test_Settlements as input. "
        "Save the output as GS_Buffer_V095_Test."
    )

    workflow = GISPlanningAgent().plan(request)

    result = WorkflowValidator().validate(
        workflow.model_dump(mode="json")
    )

    assert result["valid"] is True
    assert result["execution_enabled"] is False
    assert result["approval_required"] is True
