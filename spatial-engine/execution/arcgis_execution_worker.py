"""
GeoSentinel AI
ArcGIS Pro Execution Worker v0.6

Runs inside ArcGIS Pro Python environment.

Initial supported operation:
- Buffer

Security:
- Requires an explicitly approved job.
- Accepts only registered operation IDs.
- Resolves input layers from the current project.
- Uses the project's default geodatabase.
- Does not overwrite existing datasets.
- Does not execute arbitrary Python code.
"""

import arcpy
import json
import os
import re
import uuid
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

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4
        )


def create_result(
    job_id,
    status,
    message,
    output_path=None,
    details=None
):

    return {
        "application": "GeoSentinel AI",
        "worker_version": "0.6.0",
        "job_id": job_id,
        "status": status,
        "message": message,
        "output_path": output_path,
        "details": details or {},
        "completed_at": datetime.now(
            timezone.utc
        ).isoformat()
    }


def get_layer_by_name(map_obj, layer_name):

    matches = [
        layer
        for layer in map_obj.listLayers()
        if layer.name == layer_name
    ]

    if len(matches) == 0:

        raise ValueError(
            "Layer not found: {}".format(layer_name)
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

    input_name = inputs.get("input_features")

    if not input_name:

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
        "input_name": input_name,
        "distance": distance,
        "dissolve_option": dissolve_option,
        "output_name": output_name
    }


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

    # Verify feature count
    feature_count = int(
        arcpy.management.GetCount(input_layer)[0]
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
            "Output already exists: {}".format(output_path)
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
        arcpy.management.GetCount(output_path)[0]
    )

    # Add generated result to current map
    map_obj.addDataFromPath(output_path)

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

        job_id = job.get("job_id")

        if not job_id:

            raise ValueError(
                "Job ID is missing."
            )

        # 1. Verify approval
        validate_job_approval(job)

        # 2. Verify operation
        if job.get("operation_id") not in SUPPORTED_OPERATIONS:

            raise ValueError(
                "Operation is not supported by this worker."
            )

        # 3. Connect to current ArcGIS Pro project
        aprx = arcpy.mp.ArcGISProject("CURRENT")

        maps = aprx.listMaps()

        if not maps:

            raise RuntimeError(
                "No maps found in the current project."
            )

        map_obj = maps[0]

        # 4. Execute operation
        if job["operation_id"] == "buffer":

            details, output_path = execute_buffer(
                aprx,
                map_obj,
                job
            )

        result = create_result(
            job_id,
            "SUCCESS",
            "GIS operation executed successfully.",
            output_path,
            details
        )

    except Exception as error:

        result = create_result(
            job_id,
            "FAILED",
            str(error)
        )

        result["arcgis_messages"] = arcpy.GetMessages()

    write_json(
        RESULT_FILE,
        result
    )

    print(
        "\n========== GEOSENTINEL EXECUTION RESULT ==========\n"
    )

    print(
        json.dumps(
            result,
            indent=4
        )
    )

    print(
        "\n========== WORKER COMPLETED ==========\n"
    )


if __name__ == "__main__":

    run_worker()
