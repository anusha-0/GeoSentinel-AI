from typing import Any, Optional, TypedDict


class GeoSentinelState(TypedDict, total=False):

    user_request: str

    # Input resolution
    resolved_inputs: dict[str, dict[str, Any]]
    missing_inputs: list[str]
    input_resolution_status: str

    # Planning
    workflow: dict[str, Any]
    planning_errors: list[str]

    # Validation
    validation_result: dict[str, Any]
    validation_errors: list[str]

    # Approval
    approval_required: bool
    approval_status: str
    approval_id: Optional[str]
    approval_decision: dict[str, Any]

    # Execution
    execution_payload: dict[str, Any]
    execution_status: str
    execution_result: dict[str, Any]

    # Verification
    verification_report: dict[str, Any]
    verification_status: str

    # General
    messages: list[str]
    overall_status: str