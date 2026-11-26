"""
GeoSentinel AI
GIS Engine Abstraction
Version: 1.0.0

Defines the common execution contract for all GIS engines.

Supported implementations:
- ArcPy Engine
- Open-Source GeoPandas Engine

This module does not execute GIS operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


# ---------------------------------------------------------
# EXECUTION REQUEST
# ---------------------------------------------------------

@dataclass(frozen=True)
class ExecutionRequest:
    """
    Standardized request accepted by every GIS engine.

    The request must originate from an approved workflow.
    """

    job_id: str
    workflow_id: str
    approval_id: str
    approval_status: str

    operation_id: str
    engine: str

    inputs: Mapping[str, Any]
    parameters: Mapping[str, Any]

    output_path: str

    def validate(self) -> None:
        """Validate mandatory execution information."""

        required_fields = {
            "job_id": self.job_id,
            "workflow_id": self.workflow_id,
            "approval_id": self.approval_id,
            "operation_id": self.operation_id,
            "engine": self.engine,
            "output_path": self.output_path,
        }

        for field_name, value in required_fields.items():

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Invalid or missing field: {field_name}"
                )

        if self.approval_status != "APPROVED":
            raise PermissionError(
                "GIS execution requires explicit workflow approval."
            )

        if not isinstance(self.inputs, Mapping):
            raise ValueError("Execution inputs must be a mapping.")

        if not isinstance(self.parameters, Mapping):
            raise ValueError("Execution parameters must be a mapping.")

        if not self.inputs:
            raise ValueError("At least one execution input is required.")


# ---------------------------------------------------------
# EXECUTION RESULT
# ---------------------------------------------------------

@dataclass
class ExecutionResult:
    """
    Standardized result returned by every GIS engine.
    """

    job_id: str
    workflow_id: str
    approval_id: str

    engine: str
    engine_version: str

    operation_id: str
    status: str

    message: str
    output_path: str | None = None

    details: dict[str, Any] = field(default_factory=dict)

    completed_at: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert execution result into a JSON-compatible dictionary."""

        return {
            "job_id": self.job_id,
            "workflow_id": self.workflow_id,
            "approval_id": self.approval_id,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "operation_id": self.operation_id,
            "status": self.status,
            "message": self.message,
            "output_path": self.output_path,
            "details": self.details,
            "completed_at": self.completed_at,
        }


# ---------------------------------------------------------
# BASE GIS EXECUTION ENGINE
# ---------------------------------------------------------

class BaseGISExecutionEngine(ABC):
    """
    Abstract interface for all GeoSentinel GIS engines.

    Every engine must implement:
    - Availability detection
    - Capability reporting
    - GIS operation execution
    """

    engine_name: str = "base"
    engine_version: str = "1.0.0"

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check whether the GIS engine is available.

        Examples:
        - ArcPy installation and license availability.
        - GeoPandas and its dependencies being importable.
        """

        raise NotImplementedError

    @abstractmethod
    def supported_operations(self) -> list[str]:
        """
        Return the operations supported by this engine.
        """

        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        request: ExecutionRequest
    ) -> ExecutionResult:
        """
        Execute an approved GIS operation.

        Implementations must:
        - Validate the request.
        - Confirm operation support.
        - Respect the approved output destination.
        - Never silently overwrite existing outputs.
        - Return a standardized execution result.
        """

        raise NotImplementedError

    def can_execute(self, operation_id: str) -> bool:
        """Check whether this engine supports an operation."""

        return (
            self.is_available()
            and operation_id in self.supported_operations()
        )