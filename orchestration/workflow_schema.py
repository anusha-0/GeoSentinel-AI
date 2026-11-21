from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class WorkflowStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    operation_id: str
    description: str

    inputs: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)

    output_name: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)

    status: StepStatus = StepStatus.PENDING


class GISWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    request: str

    title: str
    description: str

    status: WorkflowStatus = WorkflowStatus.DRAFT

    steps: list[WorkflowStep]

    approval_required: bool = True
    approval_id: Optional[str] = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    metadata: dict[str, Any] = Field(default_factory=dict)