"""Expose only execution and verification artifacts for the current bridge job."""
from backend.services.execution_bridge import ExecutionBridge


class VerificationService:
    def __init__(self, bridge=None):
        self.bridge = bridge or ExecutionBridge()

    def get_status(self):
        job = self.bridge._read(self.bridge.job_file)
        execution = self.bridge.get_execution()
        report = self.bridge.get_verification()

        current_job_id = (job or {}).get("job_id")
        execution_matches = bool(
            current_job_id and execution and execution.get("job_id") == current_job_id
        )
        report_matches = bool(
            current_job_id and report and report.get("job_id") == current_job_id
        )

        # Never present a previous job's report as verification of the current job.
        current_execution = execution if execution_matches else None
        current_report = report if report_matches else None

        if not job:
            verification_status = "NO_JOB"
        elif not execution_matches:
            verification_status = "AWAITING_EXECUTION"
        elif execution.get("status") != "SUCCESS":
            verification_status = "EXECUTION_FAILED"
        elif not report_matches:
            verification_status = "AWAITING_VERIFICATION"
        else:
            verification_status = report.get("verification_status", "UNKNOWN")

        return {
            "job": job,
            "execution": current_execution,
            "verification": current_report,
            "verification_status": verification_status,
            "job_id": current_job_id
        }
