"""
GeoSentinel AI
GIS Result Verification Engine v0.7

Independently verifies ArcGIS Pro execution results.

Runs inside ArcGIS Pro Python 3.13.
"""

import arcpy
import json
import os

from verification.verification_rules import (
    inspect_feature_class,
    validate_geometry
)

from verification.report_generator import (
    VerificationReportGenerator
)


BRIDGE_DIR = r"D:\GeoSentinel-AI\runtime\bridge"

JOB_FILE = os.path.join(
    BRIDGE_DIR,
    "approved_job.json"
)

EXECUTION_RESULT_FILE = os.path.join(
    BRIDGE_DIR,
    "execution_result.json"
)

REPORT_FILE = os.path.join(
    BRIDGE_DIR,
    "verification_report.json"
)


class GISResultVerifier:

    def __init__(self):

        self.generator = VerificationReportGenerator()

    # -------------------------------------------------
    # LOAD JSON
    # -------------------------------------------------

    @staticmethod
    def load_json(path):

        if not os.path.exists(path):

            raise FileNotFoundError(
                "Required file not found: {}".format(path)
            )

        with open(path, "r", encoding="utf-8") as file:

            return json.load(file)

    # -------------------------------------------------
    # NORMALIZE VALUES
    # -------------------------------------------------

    @staticmethod
    def normalize(value):

        if isinstance(value, str):
            return " ".join(value.strip().lower().split())

        return value

    # -------------------------------------------------
    # ADD CHECK
    # -------------------------------------------------

    def add_check(self, check):

        self.generator.add_check(
            check_name=check["check"],
            status=check["status"],
            message=check["message"],
            expected=check.get("expected"),
            actual=check.get("actual")
        )

    # -------------------------------------------------
    # VERIFY JOB ID
    # -------------------------------------------------

    def verify_job_identity(self, job, execution):

        expected = job.get("job_id")
        actual = execution.get("job_id")

        matched = expected == actual

        self.generator.add_check(
            "job_identity",
            "PASS" if matched else "FAIL",
            "Job identifiers match."
            if matched else "Job identifiers do not match.",
            expected,
            actual
        )

    # -------------------------------------------------
    # VERIFY EXECUTION STATUS
    # -------------------------------------------------

    def verify_execution_status(self, execution):

        status = execution.get("status")

        passed = status == "SUCCESS"

        self.generator.add_check(
            "execution_status",
            "PASS" if passed else "FAIL",
            "GIS execution completed successfully."
            if passed else "GIS execution was unsuccessful.",
            "SUCCESS",
            status
        )

        return passed

    # -------------------------------------------------
    # VERIFY APPROVED PARAMETERS
    # -------------------------------------------------

    def verify_parameters(self, job, execution):

        requested = job.get("parameters", {})
        actual = execution.get("details", {})

        comparisons = [
            (
                "buffer_distance",
                requested.get("distance"),
                actual.get("buffer_distance")
            ),
            (
                "dissolve_option",
                requested.get("dissolve_option", "NONE"),
                actual.get("dissolve_option")
            )
        ]

        for name, expected, received in comparisons:

            matched = (
                self.normalize(expected)
                == self.normalize(received)
            )

            self.generator.add_check(
                name,
                "PASS" if matched else "FAIL",
                "Execution metadata matches approved request."
                if matched else "Execution metadata mismatch.",
                expected,
                received
            )

    # -------------------------------------------------
    # VERIFY OUTPUT PATH
    # -------------------------------------------------

    def verify_output_path(self, job, execution, aprx):

        output_gdb = aprx.defaultGeodatabase

        expected_path = os.path.normcase(
            os.path.normpath(
                os.path.join(
                    output_gdb,
                    job["output_name"]
                )
            )
        )

        actual_path = os.path.normcase(
            os.path.normpath(
                execution.get("output_path", "")
            )
        )

        matched = expected_path == actual_path

        self.generator.add_check(
            "output_path",
            "PASS" if matched else "FAIL",
            "Output path matches approved destination."
            if matched else "Output path mismatch.",
            expected_path,
            actual_path
        )

        return expected_path if matched else None

    # -------------------------------------------------
    # MAIN VERIFICATION
    # -------------------------------------------------

    def verify(self):

        job = self.load_json(JOB_FILE)

        execution = self.load_json(
            EXECUTION_RESULT_FILE
        )

        job_id = job.get("job_id")

        operation_id = job.get("operation_id")

        self.verify_job_identity(job, execution)

        execution_success = self.verify_execution_status(
            execution
        )

        # Stop if execution failed or job identity is invalid.
        if (
            not execution_success
            or job_id != execution.get("job_id")
        ):

            report = self.generator.generate_report(
                job_id,
                operation_id,
                execution.get("status", "UNKNOWN")
            )

            self.generator.save_report(
                report,
                REPORT_FILE
            )

            return report

        if job.get("approval_status") != "APPROVED":

            self.generator.add_check(
                "approval_status",
                "FAIL",
                "Original job is not approved.",
                "APPROVED",
                job.get("approval_status")
            )

            report = self.generator.generate_report(
                job_id,
                operation_id,
                execution.get("status")
            )

            self.generator.save_report(report, REPORT_FILE)

            return report

        # Currently supported verification operation.
        if operation_id != "buffer":

            self.generator.add_check(
                "operation_support",
                "NOT_RUN",
                "Verification is not implemented for this operation.",
                "buffer",
                operation_id
            )

            report = self.generator.generate_report(
                job_id,
                operation_id,
                execution.get("status")
            )

            self.generator.save_report(report, REPORT_FILE)

            return report

        self.verify_parameters(job, execution)

        aprx = arcpy.mp.ArcGISProject("CURRENT")

        output_path = self.verify_output_path(
            job,
            execution,
            aprx
        )

        output_details = {}

        if output_path:

            checks, output_details = inspect_feature_class(
                output_path,
                expected_geometry_type="Polygon"
            )

            for check in checks:
                self.add_check(check)

            # Independent geometry validation.
            geometry_check = validate_geometry(
                output_path
            )

            self.add_check(geometry_check)

        else:

            self.generator.add_check(
                "dataset_inspection",
                "NOT_RUN",
                "Dataset inspection skipped because output path validation failed."
            )

        # Generate final report.
        report = self.generator.generate_report(
            job_id=job_id,
            operation_id=operation_id,
            execution_status=execution.get("status"),
            output_details=output_details
        )

        self.generator.save_report(
            report,
            REPORT_FILE
        )

        return report


# -----------------------------------------------------
# EXECUTION
# -----------------------------------------------------

def main():

    print(
        "\n========== GEOSENTINEL RESULT VERIFICATION v0.7 ==========\n"
    )

    verifier = GISResultVerifier()

    try:

        report = verifier.verify()

        print(
            json.dumps(
                report,
                indent=4
            )
        )

        print(
            "\nVerification report saved:"
        )

        print(REPORT_FILE)

    except Exception as error:

        print(
            "\nVERIFICATION ENGINE ERROR:"
        )

        print(str(error))

        raise


if __name__ == "__main__":

    main()