"""
GeoSentinel AI - GIS Result Verification Engine v0.8.6

Runs ONLY inside ArcGIS Pro Python. It independently verifies the latest
approved_job.json against execution_result.json and inspects the real output.
"""

import arcpy
import json
import os

from verification.verification_rules import (
    inspect_feature_class,
    validate_geometry,
)
from verification.report_generator import VerificationReportGenerator


BRIDGE_DIR = r"D:\GeoSentinel-AI\runtime\bridge"
JOB_FILE = os.path.join(BRIDGE_DIR, "approved_job.json")
EXECUTION_RESULT_FILE = os.path.join(BRIDGE_DIR, "execution_result.json")
REPORT_FILE = os.path.join(BRIDGE_DIR, "verification_report.json")


class GISResultVerifier:
    def __init__(self):
        self.generator = VerificationReportGenerator()

    @staticmethod
    def load_json(path):
        if not os.path.exists(path):
            raise FileNotFoundError("Required file not found: {}".format(path))
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def normalize(value):
        if isinstance(value, str):
            return " ".join(value.strip().lower().split())
        return value

    def add_check(self, name, passed, message, expected, actual):
        self.generator.add_check(
            name, "PASS" if passed else "FAIL", message, expected, actual
        )

    def verify(self):
        # A new generator per run prevents checks leaking between reports.
        self.generator = VerificationReportGenerator()
        job = self.load_json(JOB_FILE)
        execution = self.load_json(EXECUTION_RESULT_FILE)

        job_id = job.get("job_id")
        operation_id = job.get("operation_id")
        execution_status = execution.get("status", "UNKNOWN")

        identity_ok = bool(job_id) and job_id == execution.get("job_id")
        self.add_check(
            "job_identity",
            identity_ok,
            "Job identifiers match." if identity_ok
            else "Approved job and execution result refer to different jobs.",
            job_id,
            execution.get("job_id"),
        )

        approval_ok = (
            job.get("approval_status") == "APPROVED"
            and bool(job.get("approval_id"))
        )
        self.add_check(
            "approval_status",
            approval_ok,
            "Approved job has an approval ID." if approval_ok
            else "Job approval is missing or invalid.",
            "APPROVED with approval_id",
            {
                "approval_status": job.get("approval_status"),
                "approval_id": job.get("approval_id"),
            },
        )

        execution_ok = execution_status == "SUCCESS"
        self.add_check(
            "execution_status",
            execution_ok,
            "GIS execution completed successfully." if execution_ok
            else "GIS execution was unsuccessful.",
            "SUCCESS",
            execution_status,
        )

        if not (identity_ok and approval_ok and execution_ok):
            report = self.generator.generate_report(
                job_id, operation_id, execution_status,
                workflow_id=job.get("workflow_id"), approval_id=job.get("approval_id")
            )
            self.generator.save_report(report, REPORT_FILE)
            return report

        if operation_id != "buffer":
            self.generator.add_check(
                "operation_support",
                "NOT_RUN",
                "Verification is not implemented for this operation.",
                "buffer",
                operation_id,
            )
            report = self.generator.generate_report(
                job_id, operation_id, execution_status,
                workflow_id=job.get("workflow_id"), approval_id=job.get("approval_id")
            )
            self.generator.save_report(report, REPORT_FILE)
            return report

        requested = job.get("parameters", {})
        actual_details = execution.get("details", {})

        for check_name, expected, actual in [
            (
                "buffer_distance",
                requested.get("distance"),
                actual_details.get("buffer_distance"),
            ),
            (
                "dissolve_option",
                requested.get("dissolve_option", "NONE"),
                actual_details.get("dissolve_option"),
            ),
        ]:
            matched = self.normalize(expected) == self.normalize(actual)
            self.add_check(
                check_name,
                matched,
                "Execution metadata matches approved request."
                if matched else "Execution metadata mismatch.",
                expected,
                actual,
            )

        aprx = arcpy.mp.ArcGISProject("CURRENT")
        output_gdb = aprx.defaultGeodatabase

        output_name = job.get("output_name")
        # Output names must be a single geodatabase item, not a path.
        safe_output_name = (
            isinstance(output_name, str)
            and bool(output_name.strip())
            and os.path.basename(output_name) == output_name
            and "/" not in output_name
            and "\\" not in output_name
        )

        expected_path = (
            os.path.normcase(os.path.normpath(os.path.join(output_gdb, output_name)))
            if safe_output_name else ""
        )
        actual_path = os.path.normcase(
            os.path.normpath(execution.get("output_path") or "")
        )
        path_ok = bool(expected_path and actual_path) and expected_path == actual_path

        self.add_check(
            "output_path",
            path_ok,
            "Output path matches approved destination."
            if path_ok else "Output path does not match the approved destination.",
            expected_path or "A valid geodatabase dataset name",
            actual_path,
        )

        output_details = {}
        if path_ok:
            checks, output_details = inspect_feature_class(
                expected_path, expected_geometry_type="Polygon"
            )
            for check in checks:
                self.generator.add_check(
                    check["check"],
                    check["status"],
                    check["message"],
                    check.get("expected"),
                    check.get("actual"),
                )

            geometry_check = validate_geometry(expected_path)
            self.generator.add_check(
                geometry_check["check"],
                geometry_check["status"],
                geometry_check["message"],
                geometry_check.get("expected"),
                geometry_check.get("actual"),
            )
            if geometry_check.get("cleanup_status") == "WARNING":
                self.generator.add_check(
                    "temporary_table_cleanup",
                    "WARNING",
                    "Geometry validation completed, but temporary diagnostic cleanup reported a warning.",
                    "No temporary geometry-check table or map reference remains",
                    geometry_check.get("message"),
                )
        else:
            self.generator.add_check(
                "dataset_inspection",
                "NOT_RUN",
                "Dataset inspection skipped because output path validation failed.",
                expected_path,
                actual_path,
            )

        report = self.generator.generate_report(
            job_id, operation_id, execution_status, output_details,
            workflow_id=job.get("workflow_id"), approval_id=job.get("approval_id")
        )
        self.generator.save_report(report, REPORT_FILE)
        return report


def main():
    print("\n========== GEOSENTINEL RESULT VERIFICATION v0.8.6 ==========\n")
    verifier = GISResultVerifier()
    report = verifier.verify()
    print(json.dumps(report, indent=4))
    print("\nVerification report saved: {}".format(REPORT_FILE))


if __name__ == "__main__":
    main()
