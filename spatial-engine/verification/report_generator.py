"""
GeoSentinel AI
GIS Verification Report Generator v0.7

Responsible for:
- Building structured verification reports.
- Aggregating individual verification checks.
- Determining overall verification status.
- Generating machine-readable JSON reports.
"""

import json
import os
from datetime import datetime, timezone


APPLICATION_NAME = "GeoSentinel AI"
VERIFICATION_VERSION = "0.7.0"


class VerificationReportGenerator:

    VALID_CHECK_STATUSES = {
        "PASS",
        "WARNING",
        "FAIL",
        "NOT_RUN"
    }

    def __init__(self):

        self.checks = []

    # -----------------------------------------------------
    # ADD VERIFICATION CHECK
    # -----------------------------------------------------

    def add_check(
        self,
        check_name,
        status,
        message,
        expected=None,
        actual=None
    ):

        if status not in self.VALID_CHECK_STATUSES:

            raise ValueError(
                "Invalid verification status: {}".format(status)
            )

        check = {
            "check": check_name,
            "status": status,
            "message": message,
            "expected": expected,
            "actual": actual
        }

        self.checks.append(check)

    # -----------------------------------------------------
    # DETERMINE OVERALL STATUS
    # -----------------------------------------------------

    def determine_status(self):

        if not self.checks:

            return "NOT_VERIFIED"

        statuses = [
            check["status"]
            for check in self.checks
        ]

        if "FAIL" in statuses:

            return "FAILED"

        if "WARNING" in statuses or "NOT_RUN" in statuses:

            return "WARNING"

        return "VERIFIED"

    # -----------------------------------------------------
    # BUILD SUMMARY
    # -----------------------------------------------------

    def build_summary(self):

        return {
            "total_checks": len(self.checks),

            "passed": sum(
                check["status"] == "PASS"
                for check in self.checks
            ),

            "warnings": sum(
                check["status"] == "WARNING"
                for check in self.checks
            ),

            "failed": sum(
                check["status"] == "FAIL"
                for check in self.checks
            ),

            "not_run": sum(
                check["status"] == "NOT_RUN"
                for check in self.checks
            )
        }

    # -----------------------------------------------------
    # GENERATE REPORT
    # -----------------------------------------------------

    def generate_report(
        self,
        job_id,
        operation_id,
        execution_status,
        output_details=None
    ):

        verification_status = self.determine_status()

        return {

            "application": APPLICATION_NAME,

            "verification_version": VERIFICATION_VERSION,

            "job_id": job_id,

            "operation_id": operation_id,

            "execution_status": execution_status,

            "verification_status": verification_status,

            "output": output_details or {},

            "checks": self.checks,

            "summary": self.build_summary(),

            "verified_at": datetime.now(
                timezone.utc
            ).isoformat()

        }

    # -----------------------------------------------------
    # SAVE REPORT
    # -----------------------------------------------------

    @staticmethod
    def save_report(report, output_path):

        directory = os.path.dirname(output_path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                report,
                file,
                indent=4
            )

        return output_path