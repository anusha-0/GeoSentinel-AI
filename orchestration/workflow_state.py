from typing import Any, Optional, TypedDict


class GeoSentinelState(TypedDict, total=False):

    # User request
    user_request: str

    # Planning
    workflow: dict[str, Any]
    planning_errors: list[str]

    # Validation
    validation_result: dict[str, Any]
    validation_errors: list[str]

    # Human approval
    approval_required: bool
    approval_status: str
    approval_id: Optional[str]

    # Execution
    execution_result: dict[str, Any]
    execution_status: str

    # Verification
    verification_report: dict[str, Any]
    verification_status: str

    # Final response
    messages: list[str]
    overall_status: str