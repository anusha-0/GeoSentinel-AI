import sys
from pathlib import Path

import pytest

# Add spatial-engine to Python's module search path.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SPATIAL_ENGINE_PATH = PROJECT_ROOT / "spatial-engine"

sys.path.insert(0, str(SPATIAL_ENGINE_PATH))

from engines.base import (
    ExecutionRequest,
    ExecutionResult,
    BaseGISExecutionEngine,
)


def create_request(**overrides):

    data = {
        "job_id": "GS-TEST-001",
        "workflow_id": "GS-WF-001",
        "approval_id": "GS-APPROVAL-001",
        "approval_status": "APPROVED",
        "operation_id": "buffer",
        "engine": "opensource",
        "inputs": {
            "input_features": "data/settlements.gpkg"
        },
        "parameters": {
            "distance": "500 Meters",
            "dissolve_option": "ALL"
        },
        "output_path": "outputs/buffer.gpkg"
    }

    data.update(overrides)

    return ExecutionRequest(**data)


def test_valid_execution_request():

    request = create_request()

    request.validate()


def test_unapproved_request_is_rejected():

    request = create_request(
        approval_status="PENDING"
    )

    with pytest.raises(PermissionError):

        request.validate()


def test_missing_job_id_is_rejected():

    request = create_request(job_id="")

    with pytest.raises(ValueError):

        request.validate()


def test_empty_inputs_are_rejected():

    request = create_request(inputs={})

    with pytest.raises(ValueError):

        request.validate()


def test_execution_result_serialization():

    result = ExecutionResult(
        job_id="GS-TEST-001",
        workflow_id="GS-WF-001",
        approval_id="GS-APPROVAL-001",
        engine="opensource",
        engine_version="1.0.0",
        operation_id="buffer",
        status="SUCCESS",
        message="Execution completed.",
        output_path="outputs/buffer.gpkg",
    )

    data = result.to_dict()

    assert data["job_id"] == "GS-TEST-001"
    assert data["engine"] == "opensource"
    assert data["operation_id"] == "buffer"
    assert data["status"] == "SUCCESS"


def test_base_engine_cannot_be_instantiated():

    with pytest.raises(TypeError):

        BaseGISExecutionEngine()