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

    PLANNER_VERSION = "0.3.0"
    DEFAULT_OUTPUT_NAME = "GS_Buffer_Output"

    DATASET_NAME_PATTERN = r"[A-Za-z][A-Za-z0-9_]{0,63}"

    @classmethod
    def _validate_dataset_name(cls, name: str) -> str:

        if not re.fullmatch(cls.DATASET_NAME_PATTERN, name):
            raise ValueError(
                f"Invalid dataset name: {name}. "
                "Names must start with a letter and contain "
                "only letters, numbers and underscores, "
                "with a maximum length of 63 characters."
            )

        return name

    @classmethod
    def extract_input_name(cls, request: str):

        patterns = [
            rf"\buse\s+({cls.DATASET_NAME_PATTERN})\s+as\s+(?:the\s+)?input\b",

            rf"\binput(?:\s+features?|\s+dataset)?\s*[:=]\s*({cls.DATASET_NAME_PATTERN})\b",

            rf"\b(?:run|perform|execute)\s+(?:the\s+)?(?:buffer|analysis)\s+(?:on|using)\s+({cls.DATASET_NAME_PATTERN})\b",

            rf"\buse\s+(?:the\s+)?(?:layer|dataset|feature\s+class)\s+({cls.DATASET_NAME_PATTERN})\b",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                request,
                re.IGNORECASE
            )

            if match:
                return cls._validate_dataset_name(match.group(1))

        return "USER_SELECT_REQUIRED"

    @classmethod
    def extract_output_name(cls, request: str):

        patterns = [
            rf"\bsave\s+(?:the\s+)?output\s+as\s+({cls.DATASET_NAME_PATTERN})\b",

            rf"\boutput(?:\s+name)?\s*(?:is|:|=)\s*({cls.DATASET_NAME_PATTERN})\b",

            rf"\bcreate\s+(?:the\s+)?output\s+named\s+({cls.DATASET_NAME_PATTERN})\b",

            rf"\b([A-Za-z][A-Za-z0-9_]{{0,62}})\s+as\s+(?:the\s+)?output\b",

            rf"\bsave\s+(?:it\s+)?as\s+({cls.DATASET_NAME_PATTERN})\b",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                request,
                re.IGNORECASE
            )

            if match:
                return cls._validate_dataset_name(match.group(1))

        return cls.DEFAULT_OUTPUT_NAME

    def __init__(self):
        self.registry = OperationRegistry()

    def plan(self, user_request: str) -> GISWorkflow:

        request = user_request.strip()

        if not request:
            raise ValueError("User request cannot be empty.")

        normalized = request.lower()

        if "buffer" not in normalized:
            raise ValueError(
                "This initial planner supports buffer workflows only."
            )

        distance_match = re.search(
            r"(\d+(?:\.\d+)?)\s*[-]?\s*"
            r"(meters?|metres?|m|kilometers?|km|feet|ft)\b",
            normalized
        )

        if not distance_match:
            raise ValueError(
                "Please specify a buffer distance, "
                "for example 500 meters."
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

        input_name = self.extract_input_name(request)
        output_name = self.extract_output_name(request)

        self.registry.get_operation("buffer")

        step = WorkflowStep(
            step_id="STEP-001",
            operation_id="buffer",
            description="Create a buffer around the selected input features.",
            inputs={
                "input_features": input_name
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
                "planner_version": self.PLANNER_VERSION,
                "requires_user_input": (
                    ["input_features"]
                    if input_name == "USER_SELECT_REQUIRED"
                    else []
                )
            }
        )

        return workflow