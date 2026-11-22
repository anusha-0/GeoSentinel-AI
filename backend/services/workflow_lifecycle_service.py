"""Reconcile ArcGIS Pro bridge artifacts with a persisted LangGraph workflow."""

from __future__ import annotations

from typing import Any


class WorkflowLifecycleService:
    REQUIRED_IDS = ("job_id", "workflow_id", "approval_id")

    REQUIRED_SUMMARY_FIELDS = (
        "total_checks",
        "passed",
        "failed",
        "warnings",
        "not_run",
    )

    def __init__(self, engine, bridge):
        self.engine = engine
        self.bridge = bridge

    def synchronize(self, thread_id: str) -> dict[str, Any]:
        config = self.engine._config(thread_id)
        snapshot = self.engine.graph.get_state(config)

        if not snapshot.values:
            raise ValueError(
                f"No workflow found for thread_id '{thread_id}'."
            )

        state = snapshot.values
        payload = state.get("execution_payload") or {}

        if not payload:
            return self._result(
                "NOT_APPLICABLE",
                "Workflow has no execution handoff.",
            )

        expected = self._validate_identity(
            payload, "workflow checkpoint"
        )

        job = self.bridge._read(self.bridge.job_file)
        execution = self.bridge.get_execution()
        report = self.bridge.get_verification()

        if not job or not execution:
            return self._result(
                "AWAITING_EXECUTION",
                "Approved job or execution result is not available.",
            )

        for label, artifact in (
            ("approved job", job),
            ("execution result", execution),
        ):
            self._validate_artifact_identity(
                artifact, expected, label
            )

        if execution.get("status") not in {"SUCCESS", "FAILED"}:
            return self._result(
                "AWAITING_EXECUTION",
                "Execution result is not terminal.",
            )

        if execution["status"] == "FAILED":
            return self._apply(
                config,
                state,
                "FAILED",
                "FAILED",
                "EXECUTION_FAILED",
                execution,
                report,
            )

        if not report:
            return self._result(
                "AWAITING_VERIFICATION",
                "Verification report is not available.",
            )

        self._validate_artifact_identity(
            report, expected, "verification report"
        )

        if report.get("execution_status") != "SUCCESS":
            raise ValueError(
                "Verification report does not confirm successful execution."
            )

        verification_status = report.get("verification_status")

        if verification_status == "FAILED":
            return self._apply(
                config,
                state,
                "FAILED",
                "FAILED",
                "FAILED",
                execution,
                report,
            )

        if verification_status != "VERIFIED":
            return self._result(
                "AWAITING_VERIFICATION",
                f"Verification is not complete: {verification_status!r}.",
            )

        # Validate verification summary.
        summary = report.get("summary")

        if not isinstance(summary, dict):
            raise ValueError(
                "Verification report has no valid summary."
            )

        for field in self.REQUIRED_SUMMARY_FIELDS:
            value = summary.get(field)

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(
                    f"Verification summary field '{field}' "
                    "must be a non-negative integer."
                )

        # Ensure summary counters agree with total_checks.
        counter_total = (
            summary["passed"]
            + summary["failed"]
            + summary["warnings"]
            + summary["not_run"]
        )

        if counter_total != summary["total_checks"]:
            raise ValueError(
                "Verification summary total_checks does not match "
                "the sum of individual check statuses."
            )

        if (
            summary["failed"]
            or summary["warnings"]
            or summary["not_run"]
        ):
            raise ValueError(
                "Report says VERIFIED but contains failed, warning, "
                "or not-run checks."
            )

        return self._apply(
            config,
            state,
            "COMPLETED",
            "SUCCESS",
            "VERIFIED",
            execution,
            report,
        )

    @classmethod
    def _validate_identity(cls, artifact, label):
        if not isinstance(artifact, dict):
            raise ValueError(
                f"{label} must be a dictionary."
            )

        identity = {}

        for key in cls.REQUIRED_IDS:
            value = artifact.get(key)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{label} is missing a valid {key}."
                )

            identity[key] = value

        return identity

    @classmethod
    def _validate_artifact_identity(
        cls, artifact, expected, label
    ):
        actual = cls._validate_identity(artifact, label)

        for key in cls.REQUIRED_IDS:
            if actual[key] != expected[key]:
                raise ValueError(
                    f"{label} {key} does not match "
                    "the workflow checkpoint."
                )

    def _apply(
        self,
        config,
        state,
        workflow_status,
        step_status,
        verification_status,
        execution,
        report,
    ):
        workflow = dict(state.get("workflow") or {})
        steps = [
            dict(step)
            for step in workflow.get("steps", [])
        ]

        # The current execution bridge supports exactly one step.
        if len(steps) != 1:
            raise ValueError(
                "Lifecycle synchronization currently supports "
                "exactly one workflow step."
            )

        steps[0]["status"] = step_status

        workflow["steps"] = steps
        workflow["status"] = workflow_status

        update = {
            "workflow": workflow,
            "overall_status": workflow_status,
            "execution_status": execution.get("status"),
            "execution_result": execution,
            "verification_status": verification_status,
        }

        if report is not None:
            update["verification_report"] = report

        self.engine.graph.update_state(config, update)

        return self._result(
            workflow_status,
            "Workflow lifecycle synchronized.",
            update,
        )

    @staticmethod
    def _result(status, message, state=None):
        return {
            "synchronization_status": status,
            "message": message,
            "updated_state": state or {},
        }