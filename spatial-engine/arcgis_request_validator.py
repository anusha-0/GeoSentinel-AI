"""
GeoSentinel AI
Advanced GIS Request Validator v0.4.1

ArcGIS-specific validation for requests submitted
through the GeoSentinel GIS Operation Registry.

IMPORTANT:
This module validates requests only.
It does NOT execute GIS operations.
"""

import arcpy
import os
import re
import json
import sys


# Explicit repository path
SCRIPT_DIR = r"D:\GeoSentinel-AI\spatial-engine"

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from operation_registry import OperationRegistry


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

class ValidatorConfig:

    # Only these workspaces are allowed for output.
    # Existing datasets will never be overwritten.

    ALLOW_PROJECT_GDB = True
    ALLOW_SCRATCH_GDB = True

    # Do not allow outputs outside approved workspaces.
    REQUIRE_APPROVAL_FOR_ALL_OPERATIONS = True


# ---------------------------------------------------------
# GIS REQUEST VALIDATOR
# ---------------------------------------------------------

class ArcGISRequestValidator:

    def __init__(self):

        self.registry = OperationRegistry()

        self.aprx = arcpy.mp.ArcGISProject("CURRENT")

        self.maps = self.aprx.listMaps()

    # -----------------------------------------------------
    # GENERAL HELPERS
    # -----------------------------------------------------

    def add_issue(
        self,
        issues,
        severity,
        code,
        message,
        recommendation
    ):

        issues.append({
            "severity": severity,
            "code": code,
            "message": message,
            "recommendation": recommendation
        })

    def get_all_layers(self):

        all_layers = []

        def collect(layers):

            for layer in layers:

                if layer.isGroupLayer:

                    collect(layer.listLayers())

                else:

                    all_layers.append(layer)

        for map_obj in self.maps:

            collect(map_obj.listLayers())

        return all_layers

    # -----------------------------------------------------
    # INPUT LAYER RESOLUTION
    # -----------------------------------------------------

    def resolve_layer(self, layer_name, issues, input_name):

        if not isinstance(layer_name, str) or not layer_name.strip():

            self.add_issue(
                issues,
                "ERROR",
                "INVALID_LAYER_NAME",
                "Input {} must contain a non-empty layer name.".format(
                    input_name
                ),
                "Provide the name of a layer in the open ArcGIS Pro project."
            )

            return None

        matches = [
            layer
            for layer in self.get_all_layers()
            if layer.name == layer_name
        ]

        if len(matches) == 0:

            self.add_issue(
                issues,
                "ERROR",
                "LAYER_NOT_FOUND",
                "Layer '{}' was not found.".format(layer_name),
                "Check the layer name and confirm that the layer exists "
                "in the current ArcGIS Pro project."
            )

            return None

        if len(matches) > 1:

            self.add_issue(
                issues,
                "ERROR",
                "AMBIGUOUS_LAYER_NAME",
                "Multiple layers named '{}' were found.".format(
                    layer_name
                ),
                "Use a unique layer name or rename the duplicate layers."
            )

            return None

        layer = matches[0]

        if layer.isBroken:

            self.add_issue(
                issues,
                "ERROR",
                "BROKEN_LAYER",
                "Layer '{}' has a broken data source.".format(layer_name),
                "Repair the data source before requesting this operation."
            )

            return None

        return layer

    # -----------------------------------------------------
    # INPUT TYPE VALIDATION
    # -----------------------------------------------------

    def validate_input_type(
        self,
        layer,
        expected_type,
        input_name,
        issues
    ):

        if layer is None:
            return

        valid = False

        if expected_type == "feature_layer":

            valid = layer.isFeatureLayer

        elif expected_type == "point_layer":

            valid = (
                layer.isFeatureLayer
                and arcpy.Describe(layer).shapeType == "Point"
            )

        elif expected_type == "polygon_layer":

            valid = (
                layer.isFeatureLayer
                and arcpy.Describe(layer).shapeType == "Polygon"
            )

        elif expected_type == "raster_layer":

            valid = layer.isRasterLayer

        else:

            self.add_issue(
                issues,
                "ERROR",
                "UNSUPPORTED_INPUT_TYPE",
                "Input type '{}' is not supported by this validator.".format(
                    expected_type
                ),
                "Add an explicit validation rule for this input type."
            )

            return

        if not valid:

            self.add_issue(
                issues,
                "ERROR",
                "INPUT_TYPE_MISMATCH",
                "Input '{}' does not satisfy the required type '{}'.".format(
                    input_name,
                    expected_type
                ),
                "Provide a compatible ArcGIS Pro layer."
            )

    # -----------------------------------------------------
    # INPUT DATA VALIDATION
    # -----------------------------------------------------

    def validate_inputs(self, operation, inputs, issues):

        resolved_inputs = {}

        for input_definition in operation["inputs"]:

            input_name = input_definition["name"]

            expected_type = input_definition["type"]

            required = input_definition["required"]

            if input_name not in inputs:

                if required:

                    self.add_issue(
                        issues,
                        "ERROR",
                        "MISSING_INPUT",
                        "Required input '{}' is missing.".format(
                            input_name
                        ),
                        "Provide the required input layer."
                    )

                continue

            layer = self.resolve_layer(
                inputs[input_name],
                issues,
                input_name
            )

            if layer is not None:

                self.validate_input_type(
                    layer,
                    expected_type,
                    input_name,
                    issues
                )

                resolved_inputs[input_name] = layer

        return resolved_inputs

    # -----------------------------------------------------
    # PARAMETER VALIDATION
    # -----------------------------------------------------

    def validate_parameters(
        self,
        operation,
        parameters,
        issues
    ):

        for definition in operation["parameters"]:

            name = definition["name"]

            required = definition["required"]

            if required and name not in parameters:

                self.add_issue(
                    issues,
                    "ERROR",
                    "MISSING_PARAMETER",
                    "Required parameter '{}' is missing.".format(name),
                    "Provide the required operation parameter."
                )

                continue

            if name not in parameters:
                continue

            value = parameters[name]

            allowed_values = definition.get("allowed_values")

            if allowed_values and value not in allowed_values:

                self.add_issue(
                    issues,
                    "ERROR",
                    "INVALID_PARAMETER_VALUE",
                    "Invalid value '{}' for parameter '{}'.".format(
                        value,
                        name
                    ),
                    "Allowed values: {}".format(allowed_values)
                )

            expected_type = definition["type"]

            if expected_type == "number":

                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                ):

                    self.add_issue(
                        issues,
                        "ERROR",
                        "INVALID_PARAMETER_TYPE",
                        "Parameter '{}' must be numeric.".format(name),
                        "Provide a valid number."
                    )

            elif expected_type == "string":

                if not isinstance(value, str) or not value.strip():

                    self.add_issue(
                        issues,
                        "ERROR",
                        "INVALID_PARAMETER_TYPE",
                        "Parameter '{}' must be a non-empty string.".format(
                            name
                        ),
                        "Provide a valid string."
                    )

            # Additional validation for Buffer distance
            if name == "distance":

                if isinstance(value, str):

                    pattern = (
                        r"^\s*\d+(?:\.\d+)?\s+"
                        r"(Meters|Kilometers|Feet|Miles|"
                        r"Yards|Centimeters|Millimeters)\s*$"
                    )

                    if not re.match(
                        pattern,
                        value,
                        re.IGNORECASE
                    ):

                        self.add_issue(
                            issues,
                            "ERROR",
                            "INVALID_BUFFER_DISTANCE",
                            "Buffer distance must include a positive "
                            "number and a supported linear unit.",
                            "Example: 500 Meters."
                        )

                    else:

                        numeric_value = float(
                            value.strip().split()[0]
                        )

                        if numeric_value <= 0:

                            self.add_issue(
                                issues,
                                "ERROR",
                                "NON_POSITIVE_BUFFER_DISTANCE",
                                "Buffer distance must be greater than zero.",
                                "Provide a positive distance."
                            )

    # -----------------------------------------------------
    # OUTPUT PATH VALIDATION
    # -----------------------------------------------------

    def validate_output_path(self, output_path, issues):

        if not output_path:

            self.add_issue(
                issues,
                "ERROR",
                "MISSING_OUTPUT_PATH",
                "An output destination was not provided.",
                "Provide a new output dataset path inside an approved "
                "workspace."
            )

            return False

        if not os.path.isabs(output_path):

            self.add_issue(
                issues,
                "ERROR",
                "OUTPUT_PATH_NOT_ABSOLUTE",
                "Output path must be absolute.",
                "Provide a fully qualified output path."
            )

            return False

        normalized_output = os.path.normcase(
            os.path.normpath(output_path)
        )

        approved_workspaces = []

        if ValidatorConfig.ALLOW_PROJECT_GDB:

            if self.aprx.defaultGeodatabase:

                approved_workspaces.append(
                    self.aprx.defaultGeodatabase
                )

        if ValidatorConfig.ALLOW_SCRATCH_GDB:

            if arcpy.env.scratchGDB:

                approved_workspaces.append(
                    arcpy.env.scratchGDB
                )

        approved = False

        for workspace in approved_workspaces:

            normalized_workspace = os.path.normcase(
                os.path.normpath(workspace)
            )

            try:

                relative_path = os.path.relpath(
                    normalized_output,
                    normalized_workspace
                )

                if (
                    relative_path != os.pardir
                    and not relative_path.startswith(
                        os.pardir + os.sep
                    )
                ):

                    approved = True
                    break

            except ValueError:
                continue

        if not approved:

            self.add_issue(
                issues,
                "ERROR",
                "UNAPPROVED_OUTPUT_WORKSPACE",
                "Output location is outside approved workspaces.",
                "Use the ArcGIS Pro project geodatabase or scratch "
                "geodatabase."
            )

            return False

        parent = os.path.dirname(output_path)

        if not arcpy.Exists(parent):

            self.add_issue(
                issues,
                "ERROR",
                "OUTPUT_WORKSPACE_NOT_FOUND",
                "Output workspace does not exist.",
                "Select an existing approved geodatabase."
            )

            return False

        if not arcpy.ValidateTableName(
            os.path.basename(output_path),
            parent
        ) == os.path.basename(output_path):

            self.add_issue(
                issues,
                "ERROR",
                "INVALID_OUTPUT_NAME",
                "Output dataset name is not valid for this workspace.",
                "Use a valid ArcGIS dataset name."
            )

            return False

        if arcpy.Exists(output_path):

            self.add_issue(
                issues,
                "ERROR",
                "OUTPUT_ALREADY_EXISTS",
                "The requested output already exists.",
                "Choose a new output name. Existing datasets will "
                "not be overwritten."
            )

            return False

        return True

    # -----------------------------------------------------
    # EXTENSION VALIDATION
    # -----------------------------------------------------

    def validate_extensions(self, operation, issues):

        required_extensions = operation.get(
            "required_extensions_any_of",
            []
        )

        if not required_extensions:
            return

        extension_map = {
            "Spatial Analyst": "Spatial",
            "3D Analyst": "3D",
            "Network Analyst": "Network"
        }

        available = []

        for extension_name in required_extensions:

            extension_code = extension_map.get(extension_name)

            if not extension_code:

                self.add_issue(
                    issues,
                    "ERROR",
                    "UNKNOWN_EXTENSION",
                    "Extension '{}' is not mapped.".format(
                        extension_name
                    ),
                    "Add the correct ArcPy extension identifier."
                )

                continue

            status = arcpy.CheckExtension(extension_code)

            if status in ("Available", "CheckedOut"):

                available.append(extension_name)

        if not available:

            self.add_issue(
                issues,
                "ERROR",
                "REQUIRED_EXTENSION_UNAVAILABLE",
                "None of the required extensions are available: {}".format(
                    required_extensions
                ),
                "Check your ArcGIS Pro license and extension availability."
            )

    # -----------------------------------------------------
    # APPROVAL VALIDATION
    # -----------------------------------------------------

    def validate_approval(
        self,
        operation,
        approval_granted,
        issues
    ):

        approval_required = (
            operation.get("approval_required", True)
            or ValidatorConfig.REQUIRE_APPROVAL_FOR_ALL_OPERATIONS
        )

        if approval_required and not approval_granted:

            self.add_issue(
                issues,
                "WARNING",
                "APPROVAL_REQUIRED",
                "User approval has not been granted.",
                "Present the operation plan and request explicit approval "
                "before execution."
            )

        return approval_required

    # -----------------------------------------------------
    # MAIN VALIDATION
    # -----------------------------------------------------

    def validate_request(
        self,
        operation_id,
        inputs,
        parameters,
        output_path,
        approval_granted=False
    ):

        issues = []

        # 1. Resolve registered operation
        try:

            operation = self.registry.get_operation(
                operation_id
            )

        except ValueError as error:

            self.add_issue(
                issues,
                "ERROR",
                "UNKNOWN_OPERATION",
                str(error),
                "Select an operation registered in GeoSentinel."
            )

            return self.build_result(
                operation_id,
                issues,
                False,
                False
            )

        # 2. Validate inputs
        resolved_inputs = self.validate_inputs(
            operation,
            inputs,
            issues
        )

        # 3. Validate parameters
        self.validate_parameters(
            operation,
            parameters,
            issues
        )

        # 4. Validate output destination
        self.validate_output_path(
            output_path,
            issues
        )

        # 5. Validate ArcGIS extensions
        self.validate_extensions(
            operation,
            issues
        )

        # 6. Validate approval
        approval_required = self.validate_approval(
            operation,
            approval_granted,
            issues
        )

        # 7. Determine validation status
        has_errors = any(
            issue["severity"] == "ERROR"
            for issue in issues
        )

        has_warnings = any(
            issue["severity"] == "WARNING"
            for issue in issues
        )

        validation_passed = not has_errors

        execution_enabled = self.registry.registry.get(
            "execution_enabled",
            False
        )

        ready_for_execution = (
            validation_passed
            and not has_warnings
            and execution_enabled
            and (
                not approval_required
                or approval_granted
            )
        )

        return {

            "application": "GeoSentinel AI",

            "validator_version": "0.4.1",

            "operation_id": operation_id,

            "validation_passed": validation_passed,

            "ready_for_execution": ready_for_execution,

            "execution_enabled": execution_enabled,

            "approval_required": approval_required,

            "approval_granted": approval_granted,

            "resolved_inputs": {
                name: layer.name
                for name, layer in resolved_inputs.items()
            },

            "output_path": output_path,

            "issues": issues,

            "summary": {
                "total_issues": len(issues),

                "errors": sum(
                    issue["severity"] == "ERROR"
                    for issue in issues
                ),

                "warnings": sum(
                    issue["severity"] == "WARNING"
                    for issue in issues
                )
            }
        }

    # -----------------------------------------------------
    # RESULT BUILDER
    # -----------------------------------------------------

    def build_result(
        self,
        operation_id,
        issues,
        validation_passed,
        ready_for_execution
    ):

        return {

            "application": "GeoSentinel AI",

            "validator_version": "0.4.1",

            "operation_id": operation_id,

            "validation_passed": validation_passed,

            "ready_for_execution": ready_for_execution,

            "execution_enabled": False,

            "issues": issues

        }


# ---------------------------------------------------------
# TEST
# ---------------------------------------------------------

def main():

    validator = ArcGISRequestValidator()

    project_gdb = validator.aprx.defaultGeodatabase

    output_path = os.path.join(
        project_gdb,
        "GS_Buffer_Test"
    )

    result = validator.validate_request(

        operation_id="buffer",

        inputs={
            "input_features": "GS_Test_Settlements"
        },

        parameters={
            "distance": "500 Meters",
            "dissolve_option": "ALL"
        },

        output_path=output_path,

        approval_granted=False
    )

    print(
        "\n========== GEOSENTINEL GIS REQUEST VALIDATOR v0.4.1 ==========\n"
    )

    print(
        json.dumps(
            result,
            indent=4
        )
    )

    print(
        "\n========== VALIDATION COMPLETED ==========\n"
    )


if __name__ == "__main__":

    main()