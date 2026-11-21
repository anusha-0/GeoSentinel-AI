import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPATIAL_ENGINE_DIR = PROJECT_ROOT / "spatial-engine"

if str(SPATIAL_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(SPATIAL_ENGINE_DIR))

from operation_registry import OperationRegistry


UNRESOLVED_VALUES = {
    "USER_SELECT_REQUIRED",
    "USER_INPUT_REQUIRED",
    "NOT_PROVIDED",
    "UNKNOWN",
    "TBD",
    ""
}


class WorkflowValidator:

    def __init__(self):
        self.registry = OperationRegistry()

    def validate(self, workflow: dict[str, Any]) -> dict[str, Any]:

        errors = []
        validated_steps = []

        steps = workflow.get("steps", [])

        if not steps:
            return {
                "valid": False,
                "errors": ["Workflow contains no steps."],
                "validated_steps": []
            }

        step_ids = [step.get("step_id") for step in steps]

        if None in step_ids:
            errors.append("Every workflow step must have a step_id.")

        if len(step_ids) != len(set(step_ids)):
            errors.append("Duplicate workflow step IDs detected.")

        known_ids = set(step_ids)

        for step in steps:

            step_id = step.get("step_id", "UNKNOWN")
            operation_id = step.get("operation_id")

            if not operation_id:
                errors.append(f"{step_id}: Missing operation_id.")
                continue

            # Validate dependencies.
            for dependency in step.get("depends_on", []):

                if dependency not in known_ids:
                    errors.append(
                        f"{step_id}: Unknown dependency '{dependency}'."
                    )

            inputs = step.get("inputs", {})
            parameters = step.get("parameters", {})

            # Reject unresolved required or optional input placeholders.
            for input_name, input_value in inputs.items():

                if isinstance(input_value, str):
                    if input_value.strip().upper() in UNRESOLVED_VALUES:
                        errors.append(
                            f"{step_id}: Input '{input_name}' "
                            "requires user selection."
                        )

            # Registry-level validation.
            try:

                result = self.registry.validate_request(
                    operation_id=operation_id,
                    inputs=inputs,
                    parameters=parameters
                )

                if not result.get("valid", False):

                    errors.extend(
                        f"{step_id}: {error}"
                        for error in result.get("errors", [])
                    )

                else:
                    validated_steps.append(step_id)

            except Exception as exc:
                errors.append(f"{step_id}: {str(exc)}")

        valid = len(errors) == 0

        return {
            "valid": valid,
            "errors": errors,
            "validated_steps": validated_steps,
            "approval_required": workflow.get(
                "approval_required", True
            ),
            "execution_enabled": False
        }