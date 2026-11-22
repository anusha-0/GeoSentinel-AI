"""Safe adapter between approved LangGraph workflows and ArcGIS Pro."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ExecutionBridge:

    REQUIRED_IDS = (
        "job_id",
        "workflow_id",
        "approval_id",
    )

    TERMINAL_EXECUTION_STATUSES = {
        "SUCCESS",
        "FAILED",
    }

    TERMINAL_VERIFICATION_STATUSES = {
        "VERIFIED",
        "FAILED",
        "WARNING",
    }

    def __init__(self, bridge_dir=None):

        project_root = Path(__file__).resolve().parents[2]

        self.bridge_dir = Path(
            bridge_dir
            or os.getenv(
                "GEOSENTINEL_BRIDGE_DIR",
                project_root / "runtime" / "bridge",
            )
        )

        self.job_file = self.bridge_dir / "approved_job.json"
        self.result_file = self.bridge_dir / "execution_result.json"
        self.report_file = self.bridge_dir / "verification_report.json"

        self.archive_dir = self.bridge_dir / "archive"

    # -----------------------------------------------------
    # JSON HELPERS
    # -----------------------------------------------------

    @staticmethod
    def _read(path):

        path = Path(path)

        if not path.exists():
            return None

        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _atomic_write(path, payload):

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_name = tempfile.mkstemp(
            prefix=path.stem + "_",
            suffix=".tmp",
            dir=str(path.parent),
        )

        try:

            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    payload,
                    handle,
                    indent=4,
                )

                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temp_name, path)

        finally:

            if os.path.exists(temp_name):
                os.unlink(temp_name)

    # -----------------------------------------------------
    # IDENTITY VALIDATION
    # -----------------------------------------------------

    @classmethod
    def _validate_identity(cls, artifact, label):

        if not isinstance(artifact, dict):
            raise ValueError(
                f"{label} must be a JSON object."
            )

        identity = {}

        for key in cls.REQUIRED_IDS:

            value = artifact.get(key)

            if not isinstance(value, str) or not value.strip():

                raise ValueError(
                    f"{label} is missing a valid {key}."
                )

            identity[key] = value.strip()

        return identity

    @classmethod
    def _identities_match(cls, first, second):

        try:

            first_ids = cls._validate_identity(
                first,
                "First artifact",
            )

            second_ids = cls._validate_identity(
                second,
                "Second artifact",
            )

        except ValueError:
            return False

        return first_ids == second_ids

    # -----------------------------------------------------
    # PAYLOAD VALIDATION
    # -----------------------------------------------------

    def _validate_payload(self, payload):

        if not isinstance(payload, dict):
            raise ValueError(
                "Execution payload must be an object."
            )

        identity = self._validate_identity(
            payload,
            "Execution payload",
        )

        if payload.get("approval_status") != "APPROVED":
            raise PermissionError(
                "Only explicitly approved workflows can be handed to ArcGIS Pro."
            )

        steps = payload.get("steps")

        if not isinstance(steps, list) or len(steps) != 1:
            raise ValueError(
                "The current ArcGIS Pro worker supports exactly one workflow step."
            )

        step = steps[0]

        if not isinstance(step, dict):
            raise ValueError(
                "Workflow step must be an object."
            )

        if step.get("operation_id") != "buffer":
            raise ValueError(
                "The current ArcGIS Pro worker supports the buffer operation only."
            )

        output_name = step.get("output_name")

        if (
            not isinstance(output_name, str)
            or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_]{0,63}",
                output_name,
            )
        ):
            raise ValueError(
                "Invalid output dataset name."
            )

        inputs = step.get("inputs")

        if not isinstance(inputs, dict):
            raise ValueError(
                "Workflow inputs must be an object."
            )

        input_features = inputs.get("input_features")

        if (
            not isinstance(input_features, str)
            or not input_features.strip()
            or input_features.strip().upper()
            in {
                "USER_SELECT_REQUIRED",
                "USER_INPUT_REQUIRED",
                "NOT_PROVIDED",
                "UNKNOWN",
                "TBD",
            }
        ):
            raise ValueError(
                "A valid input feature layer is required."
            )

        parameters = step.get("parameters", {})

        if not isinstance(parameters, dict):
            raise ValueError(
                "Workflow parameters must be an object."
            )

        return {
            **identity,
            "operation_id": "buffer",
            "approval_status": "APPROVED",
            "execution_status": "PENDING",
            "inputs": inputs,
            "parameters": parameters,
            "output_name": output_name,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    # -----------------------------------------------------
    # PREVIOUS JOB HANDLING
    # -----------------------------------------------------

    def _is_previous_job_terminal(
        self,
        job,
        execution,
        report,
    ):

        if not job:
            return True

        job_status = job.get("execution_status")

        # A failed execution is terminal only when its matching
        # execution result confirms the failure.
        if job_status == "FAILED":

            return (
                execution is not None
                and execution.get("status") == "FAILED"
                and self._identities_match(job, execution)
            )

        # A successful execution is terminal only after its
        # matching verification report is available.
        if job_status == "SUCCESS":

            return (
                execution is not None
                and execution.get("status") == "SUCCESS"
                and self._identities_match(job, execution)
                and report is not None
                and self._identities_match(job, report)
                and report.get("verification_status") in {
                    "VERIFIED",
                    "FAILED",
                }
            )

        # Backward compatibility with worker versions that left
        # approved_job.json marked PENDING after execution.
        if job_status == "PENDING":

            if execution is None:
                return False

            if not self._identities_match(job, execution):
                return False

            execution_status = execution.get("status")

            if execution_status == "FAILED":
                return True

            if execution_status == "SUCCESS":

                return (
                    report is not None
                    and self._identities_match(job, report)
                    and report.get("verification_status") in {
                        "VERIFIED",
                        "FAILED",
                    }
                )

        return False

    def _archive_existing_artifacts(self):

        existing_files = [
            self.job_file,
            self.result_file,
            self.report_file,
        ]

        present = [
            path
            for path in existing_files
            if path.exists()
        ]

        if not present:
            return None

        timestamp = datetime.now(
            timezone.utc
        ).strftime("%Y%m%dT%H%M%S%fZ")

        job = self._read(self.job_file) or {}

        job_id = job.get("job_id", "orphan")

        safe_job_id = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            str(job_id),
        )

        destination = (
            self.archive_dir
            / f"{safe_job_id}_{timestamp}"
        )

        destination.mkdir(
            parents=True,
            exist_ok=False,
        )

        try:

            for source in present:

                shutil.move(
                    str(source),
                    str(destination / source.name),
                )

        except Exception:

            # Best-effort rollback if archival is interrupted.
            for archived in destination.iterdir():

                original = self.bridge_dir / archived.name

                if not original.exists():
                    shutil.move(
                        str(archived),
                        str(original),
                    )

            raise

        return destination

    # -----------------------------------------------------
    # PUBLISH APPROVED JOB
    # -----------------------------------------------------

    def publish(self, payload):

        job = self._validate_payload(payload)

        self.bridge_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        existing_job = self._read(self.job_file)
        existing_execution = self._read(self.result_file)
        existing_report = self._read(self.report_file)

        if not self._is_previous_job_terminal(
            existing_job,
            existing_execution,
            existing_report,
        ):

            raise FileExistsError(
                "An uncompleted ArcGIS job already occupies the bridge. "
                "Complete execution and required verification before publishing another job."
            )

        self._archive_existing_artifacts()

        self._atomic_write(
            self.job_file,
            job,
        )

        return job

    # -----------------------------------------------------
    # ARTIFACT ACCESS
    # -----------------------------------------------------

    def get_job(self):
        return self._read(self.job_file)

    def get_execution(self):
        return self._read(self.result_file)

    def get_verification(self):
        return self._read(self.report_file)