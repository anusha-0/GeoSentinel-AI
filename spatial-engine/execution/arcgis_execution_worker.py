"""
GeoSentinel AI
ArcGIS Pro Execution Worker v0.6.2

Runs inside ArcGIS Pro Python environment.

Initial supported operation:
- Buffer

Security:
- Requires an explicitly approved job.
- Requires valid job, workflow, and approval identities.
- Accepts only registered operation IDs.
- Resolves input layers from the current project.
- Uses the project's default geodatabase.
- Does not overwrite existing datasets.
- Does not execute arbitrary Python code.
- Writes execution artifacts atomically.
"""

import arcpy
import json
import os
import re
import tempfile

from datetime import datetime, timezone


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

BRIDGE_DIR = r"D:\GeoSentinel-AI\runtime\bridge"

REQUEST_FILE = os.path.join(
    BRIDGE_DIR,
    "approved_job.json"
)

RESULT_FILE = os.path.join(
    BRIDGE_DIR,
    "execution_result.json"
)

SUPPORTED_OPERATIONS = [
    "buffer"
]


# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def write_json(path, data):
    """
    Atomically write JSON to prevent partially written artifacts.

    The temporary file is created in the destination directory
    so os.replace() operates on the same filesystem.
    """

    directory = os.path.dirname(
        os.path.abspath(path)
    )

    os.makedirs(
        directory,
        exist_ok=True
    )

    fd, temp_path = tempfile.mkstemp(
        prefix="geosentinel_",
        suffix=".tmp",
        dir=directory
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=4
            )

            file.flush()
            os.fsync(file.fileno())

        os.replace(
            temp_path,
            path
        )

    finally:

        if os.path.exists(temp_path):
            os.remove(temp_path)


def create_result(
    job_id,
    status,
    message,
    output_path=None,
    details=None,
    workflow_id=None,
    approval_id=None
):
    """
    Create a standardized execution result.

    All workflow identities are preserved so that the backend
    can correlate execution and verification artifacts.
    """

    return {
        "application": "GeoSentinel AI",
        "worker_version": "0.6.2",
        "job_id": job_id,
        "workflow_id": workflow_id,
        "approval_id": approval_id,
        "status": status,
        "message": message,
        "output_path": output_path,
        "details": details or {},
        "completed_at": datetime.now(
            timezone.utc
        ).isoformat()
    }


def validate_job_identity(job):
    """
    Require all three identifiers for execution.
    """

    if not isinstance(job, dict):

        raise ValueError(
            "Execution job must be a JSON object."
        )

    required_ids = (
        "job_id",
        "workflow_id",
        "approval_id"
    )

    for key in required_ids:

        value = job.get(key)

        if not isinstance(value, str) or not value.strip():

            raise ValueError(
                "Execution job is missing a valid {}.".format(
                    key
                )
            )

    return {
        key: job[key].strip()
        for key in required_ids
    }


def update_job_status(job, status):
    """
    Update approved_job.json only if it still belongs
    to the same job and is currently pending.
    """

    if status not in ("SUCCESS", "FAILED"):

        raise ValueError(
            "Invalid terminal execution status."
        )

    if not os.path.exists(REQUEST_FILE):

        raise FileNotFoundError(
            "Approved job file disappeared during execution."
        )

    with open(
        REQUEST_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        current_job = json.load(file)

    expected_identity = validate_job_identity(job)

    current_identity = validate_job_identity(
        current_job
    )

    if current_identity != expected_identity:

        raise RuntimeError(
            "Approved job identity changed during execution. "
            "Status update rejected."
        )

    if current_job.get("approval_status") != "APPROVED":

        raise PermissionError(
            "Approved job status changed during execution."
        )

    if current_job.get("execution_status") != "PENDING":

        raise RuntimeError(
            "Job is no longer pending. Status update rejected."
        )

    current_job["execution_status"] = status

    current_job["completed_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    write_json(
        REQUEST_FILE,
        current_job
    )

    print(
        "Approved job status updated: {}".format(
            status
        )
    )


def get_layer_by_name(map_obj, layer_name):
    """
    Resolve exactly one layer by name.
    """

    matches = [
        layer
        for layer in map_obj.listLayers()
        if layer.name == layer_name
    ]

    if len(matches) == 0:

        raise ValueError(
            "Layer not found: {}".format(
                layer_name
            )
        )

    if len(matches) > 1:

        raise ValueError(
            "Multiple layers found with name: {}".format(
                layer_name
            )
        )

    return matches[0]


# ---------------------------------------------------------
# APPROVAL VALIDATION
# ---------------------------------------------------------

def validate_job_approval(job):

    if job.get("approval_status") != "APPROVED":

        raise PermissionError(
            "Execution blocked: job has not been approved."
        )

    if job.get("execution_status") != "PENDING":

        raise PermissionError(
            "Execution blocked: job is not pending."
        )

    if not job.get("approval_id"):

        raise PermissionError(
            "Execution blocked: approval ID is missing."
        )


# ---------------------------------------------------------
# BUFFER VALIDATION
# ---------------------------------------------------------

def validate_buffer_request(job):

    if job.get("operation_id") != "buffer":

        raise ValueError(
            "Unsupported operation: {}".format(
                job.get("operation_id")
            )
        )

    inputs = job.get("inputs", {})

    parameters = job.get("parameters", {})

    if not isinstance(inputs, dict):

        raise ValueError(
            "Buffer inputs must be an object."
        )

    if not isinstance(parameters, dict):

        raise ValueError(
            "Buffer parameters must be an object."
        )

    input_name = inputs.get("input_features")

    if not isinstance(input_name, str) or not input_name.strip():

        raise ValueError(
            "Buffer input feature layer is missing."
        )

    distance = parameters.get("distance")

    if not isinstance(distance, str):

        raise ValueError(
            "Buffer distance must be a string."
        )

    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s+"
        r"(Meters|Kilometers|Feet|Miles|Yards)\s*",
        distance,
        re.IGNORECASE
    )

    if not match:

        raise ValueError(
            "Invalid buffer distance. Example: 500 Meters."
        )

    if float(match.group(1)) <= 0:

        raise ValueError(
            "Buffer distance must be greater than zero."
        )

    dissolve_option = parameters.get(
        "dissolve_option",
        "NONE"
    )

    if dissolve_option not in ("NONE", "ALL"):

        raise ValueError(
            "Invalid dissolve option."
        )

    output_name = job.get("output_name")

    if not output_name:

        raise ValueError(
            "Output dataset name is missing."
        )

    if not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_]{0,63}",
        output_name
    ):

        raise ValueError(
            "Invalid output dataset name."
        )

    return {
        "input_name": input_name.strip(),
        "distance": distance,
        "dissolve_option": dissolve_option,
        "output_name": output_name
    }


# ---------------------------------------------------------
# PATH HELPERS
# ---------------------------------------------------------

def normalize_catalog_path(path):
    """
    Normalize a dataset path for reliable comparison.

    ArcGIS layer data sources may differ in casing
    or path separators.
    """

    return os.path.normcase(
        os.path.normpath(
            os.path.abspath(path)
        )
    )


def add_output_to_map_if_missing(map_obj, output_path):
    """
    Ensure the output dataset is represented by at most
    one layer in the target map.

    Reuse an existing layer when possible.
    """

    target_path = normalize_catalog_path(
        output_path
    )

    for layer in map_obj.listLayers():

        if layer.isBroken:
            continue

        if not layer.isFeatureLayer:
            continue

        try:

            existing_path = normalize_catalog_path(
                layer.dataSource
            )

        except (
            AttributeError,
            RuntimeError,
            OSError
        ):

            continue

        if existing_path == target_path:

            print(
                "Output already present in map; "
                "reusing existing layer: {}".format(
                    layer.name
                )
            )

            return layer

    print(
        "Adding output to map: {}".format(
            output_path
        )
    )

    return map_obj.addDataFromPath(
        output_path
    )


# ---------------------------------------------------------
# BUFFER EXECUTION
# ---------------------------------------------------------

def execute_buffer(aprx, map_obj, job):

    validated = validate_buffer_request(job)

    input_layer = get_layer_by_name(
        map_obj,
        validated["input_name"]
    )

    if input_layer.isBroken:

        raise ValueError(
            "Input layer has a broken data source."
        )

    if not input_layer.isFeatureLayer:

        raise ValueError(
            "Buffer input must be a feature layer."
        )

    # Verify input feature count

    feature_count = int(
        arcpy.management.GetCount(
            input_layer
        )[0]
    )

    if feature_count == 0:

        raise ValueError(
            "Input feature layer contains no features."
        )

    # Resolve output workspace from current project

    output_gdb = aprx.defaultGeodatabase

    if not output_gdb or not arcpy.Exists(output_gdb):

        raise RuntimeError(
            "Project default geodatabase is unavailable."
        )

    output_path = os.path.join(
        output_gdb,
        validated["output_name"]
    )

    # Never overwrite existing output

    if arcpy.Exists(output_path):

        raise FileExistsError(
            "Output already exists: {}".format(
                output_path
            )
        )

    # Explicitly disable overwriting

    arcpy.env.overwriteOutput = False

    # Execute approved ArcPy operation

    arcpy.analysis.Buffer(
        in_features=input_layer,
        out_feature_class=output_path,
        buffer_distance_or_field=validated["distance"],
        dissolve_option=validated["dissolve_option"]
    )

    if not arcpy.Exists(output_path):

        raise RuntimeError(
            "Buffer operation completed without a valid output."
        )

    output_count = int(
        arcpy.management.GetCount(
            output_path
        )[0]
    )

    # Reuse existing map layer if ArcGIS Pro
    # automatically added the output.

    add_output_to_map_if_missing(
        map_obj,
        output_path
    )

    return {
        "input_layer": input_layer.name,
        "input_feature_count": feature_count,
        "output_feature_count": output_count,
        "output_geodatabase": output_gdb,
        "output_dataset": validated["output_name"],
        "buffer_distance": validated["distance"],
        "dissolve_option": validated["dissolve_option"],
        "spatial_reference": arcpy.Describe(
            output_path
        ).spatialReference.name
    }, output_path


# ---------------------------------------------------------
# MAIN WORKER
# ---------------------------------------------------------

def run_worker():

    job_id = None
    job = {}
    result = None

    job_validated = False
    result_persisted = False

    try:

        if not os.path.exists(REQUEST_FILE):

            raise FileNotFoundError(
                "No approved execution job found."
            )

        with open(
            REQUEST_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            job = json.load(file)

        # 1. Validate workflow identity

        validate_job_identity(job)

        job_id = job["job_id"]

        # 2. Verify approval and pending status

        validate_job_approval(job)

        job_validated = True

        # 3. Verify registered operation

        if job.get("operation_id") not in SUPPORTED_OPERATIONS:

            raise ValueError(
                "Operation is not supported by this worker."
            )

        # 4. Connect to current ArcGIS Pro project

        aprx = arcpy.mp.ArcGISProject(
            "CURRENT"
        )

        maps = aprx.listMaps()

        if not maps:

            raise RuntimeError(
                "No maps found in the current project."
            )

        map_obj = maps[0]

        # 5. Execute approved operation

        if job["operation_id"] == "buffer":

            details, output_path = execute_buffer(
                aprx,
                map_obj,
                job
            )

        else:

            raise ValueError(
                "No execution handler registered for this operation."
            )

        result = create_result(
            job_id,
            "SUCCESS",
            "GIS operation executed successfully.",
            output_path,
            details,
            workflow_id=job["workflow_id"],
            approval_id=job["approval_id"]
        )

    except Exception as error:

        result = create_result(
            job_id,
            "FAILED",
            str(error),
            workflow_id=job.get("workflow_id"),
            approval_id=job.get("approval_id")
        )

        try:

            result["arcgis_messages"] = arcpy.GetMessages()

        except Exception:

            result["arcgis_messages"] = None

        print(
            "Execution error: {}".format(
                error
            )
        )

    # -----------------------------------------------------
    # 6. PERSIST EXECUTION RESULT
    # -----------------------------------------------------

    # Only jobs that passed identity and approval validation
    # can write to execution_result.json.
    #
    # Invalid or unapproved requests must never overwrite
    # an existing execution result.

    if job_validated and result is not None:

        try:

            write_json(
                RESULT_FILE,
                result
            )

            result_persisted = True

        except Exception as persistence_error:

            print(
                "CRITICAL: Execution result could not be "
                "persisted: {}".format(
                    persistence_error
                )
            )

    else:

        print(
            "Execution result was not persisted because "
            "job identity or approval validation failed."
        )

    # -----------------------------------------------------
    # 7. UPDATE APPROVED JOB STATUS
    # -----------------------------------------------------

    # Update the job only after the execution result
    # has been successfully persisted.

    if (
        job_validated
        and result_persisted
        and result is not None
    ):

        try:

            update_job_status(
                job,
                result["status"]
            )

        except Exception as status_error:

            print(
                "WARNING: Execution result was written, "
                "but approved job status could not be updated: "
                "{}".format(
                    status_error
                )
            )

    # -----------------------------------------------------
    # 8. DISPLAY FINAL RESULT
    # -----------------------------------------------------

    print(
        "\n========== GEOSENTINEL EXECUTION RESULT ==========\n"
    )

    if result is not None:

        print(
            json.dumps(
                result,
                indent=4
            )
        )

    print(
        "\n========== WORKER COMPLETED ==========\n"
    )


# ---------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":

    run_worker()