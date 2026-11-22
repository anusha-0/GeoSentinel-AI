
import re
import uuid
import sys
from pathlib import Path

from orchestration.workflow_schema import (
    GISWorkflow,
    WorkflowStep
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPATIAL_ENGINE_DIR = PROJECT_ROOT / "spatial-engine"

if str(SPATIAL_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(SPATIAL_ENGINE_DIR))

from operation_registry import OperationRegistry


class GISPlanningAgent:

    DEFAULT_OUTPUT_NAME = "GS_Buffer_Output"

    def __init__(self):
        self.registry = OperationRegistry()

    @staticmethod
    def extract_output_name(request: str) -> str:
        """
        Extract an explicitly requested output dataset name.

        Supported examples:
        - GS_Buffer_Test as the output
        - output name: GS_Buffer_Test
        - output: GS_Buffer_Test
        - save as GS_Buffer_Test
        """

        patterns = [
            r"\b([A-Za-z][A-Za-z0-9_]*)\s+as\s+(?:the\s+)?output\b",
            r"\boutput(?:\s+name)?\s*(?:is|:|=)\s*([A-Za-z][A-Za-z0-9_]*)\b",
            r"\bsave\s+(?:it\s+)?as\s+([A-Za-z][A-Za-z0-9_]*)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, request, re.IGNORECASE)

            if match:
                output_name = match.group(1)

                if not re.fullmatch(
                    r"[A-Za-z][A-Za-z0-9_]{0,159}",
                    output_name
                ):
                    raise ValueError(
                        f"Invalid output dataset name: {output_name}"
                    )

                return output_name

        return GISPlanningAgent.DEFAULT_OUTPUT_NAME

    def plan(self, user_request: str) -> GISWorkflow:

        request = user_request.strip()

        if not request:
            raise ValueError("User request cannot be empty.")

        normalized = request.lower()

        # Initial supported intent: Buffer
        if "buffer" not in normalized:
            raise ValueError(
                "This initial planner supports buffer workflows only. "
                "Additional GIS operations will be added incrementally."
            )

        distance_match = re.search(
            r"(\d+(?:\.\d+)?)\s*[-]?\s*"
            r"(meters?|metres?|m|kilometers?|km|feet|ft)\b",
            normalized
        )

        if not distance_match:
            raise ValueError(
                "Please specify a buffer distance, for example 500 meters."
            )

        distance_value = float(distance_match.group(1))
        distance_unit = distance_match.group(2)

        unit_mapping = {
            "meter": "Meters",
            "meters": "Meters",
            "metre": "Meters",
            "metres": "Meters",
            "m": "Meters",
            "kilometer": "Kilometers",
            "kilometers": "Kilometers",
            "km": "Kilometers",
            "feet": "Feet",
            "foot": "Feet",
            "ft": "Feet"
        }

        unit = unit_mapping.get(distance_unit)

        if unit is None:
            raise ValueError("Unsupported buffer distance unit.")

        distance = f"{distance_value:g} {unit}"

        dissolve_option = (
            "ALL"
            if "dissolve" in normalized
            else "NONE"
        )

        output_name = self.extract_output_name(request)

        # Confirm that the operation exists in the registry.
        self.registry.get_operation("buffer")

        step = WorkflowStep(
            step_id="STEP-001",
            operation_id="buffer",
            description="Create a buffer around the selected input features.",
            inputs={
                "input_features": "USER_SELECT_REQUIRED"
            },
            parameters={
                "distance": distance,
                "dissolve_option": dissolve_option
            },
            output_name=output_name
        )

        workflow = GISWorkflow(
            workflow_id=f"GS-WF-{uuid.uuid4().hex[:8].upper()}",
            request=request,
            title="GIS Buffer Analysis",
            description=(
                f"Create a {distance} buffer around the selected "
                f"features with dissolve option {dissolve_option}."
            ),
            steps=[step],
            approval_required=True,
            metadata={
                "planner": "deterministic",
                "planner_version": "0.2.0",
                "requires_user_input": [
                    "input_features"
                ]
            }
        )

        return workflow
