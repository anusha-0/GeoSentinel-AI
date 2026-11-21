"""
GeoSentinel AI
GIS Verification Rules v0.7

Independent inspection of ArcGIS datasets.

Runs inside ArcGIS Pro Python environment.
"""

import os
import uuid
import arcpy



def create_check(
    check_name,
    status,
    message,
    expected=None,
    actual=None
):
    return {
        "check": check_name,
        "status": status,
        "message": message,
        "expected": expected,
        "actual": actual
    }


def inspect_feature_class(
    dataset_path,
    expected_geometry_type=None
):

    checks = []
    output_details = {}

    # -------------------------------------------------
    # 1. DATASET EXISTENCE
    # -------------------------------------------------

    if not arcpy.Exists(dataset_path):

        checks.append(
            create_check(
                "output_exists",
                "FAIL",
                "Output dataset does not exist.",
                True,
                False
            )
        )

        return checks, output_details

    checks.append(
        create_check(
            "output_exists",
            "PASS",
            "Output dataset exists.",
            True,
            True
        )
    )

    # -------------------------------------------------
    # 2. DATASET DESCRIPTION
    # -------------------------------------------------

    try:

        description = arcpy.Describe(dataset_path)

        geometry_type = description.shapeType

        spatial_reference = description.spatialReference

        output_details["dataset"] = description.name

        output_details["geometry_type"] = geometry_type

        output_details["spatial_reference"] = {
            "name": spatial_reference.name,
            "factory_code": spatial_reference.factoryCode
        }

    except Exception as error:

        checks.append(
            create_check(
                "dataset_description",
                "FAIL",
                "Unable to describe output dataset: {}".format(error)
            )
        )

        return checks, output_details

    # -------------------------------------------------
    # 3. GEOMETRY TYPE
    # -------------------------------------------------

    if expected_geometry_type:

        geometry_matches = (
            geometry_type.lower()
            == expected_geometry_type.lower()
        )

        checks.append(
            create_check(
                "geometry_type",
                "PASS" if geometry_matches else "FAIL",
                (
                    "Output geometry type is correct."
                    if geometry_matches
                    else "Output geometry type does not match."
                ),
                expected_geometry_type,
                geometry_type
            )
        )

    # -------------------------------------------------
    # 4. FEATURE COUNT
    # -------------------------------------------------

    try:

        feature_count = int(
            arcpy.management.GetCount(dataset_path)[0]
        )

        output_details["feature_count"] = feature_count

        checks.append(
            create_check(
                "feature_count",
                "PASS" if feature_count > 0 else "FAIL",
                (
                    "Output contains features."
                    if feature_count > 0
                    else "Output dataset is empty."
                ),
                "> 0",
                feature_count
            )
        )

    except Exception as error:

        checks.append(
            create_check(
                "feature_count",
                "FAIL",
                "Unable to retrieve feature count: {}".format(error)
            )
        )

    # -------------------------------------------------
    # 5. SPATIAL REFERENCE
    # -------------------------------------------------

    spatial_reference_name = spatial_reference.name

    spatial_reference_valid = (
        spatial_reference_name
        not in (None, "", "Unknown")
    )

    checks.append(
        create_check(
            "spatial_reference",
            "PASS" if spatial_reference_valid else "FAIL",
            (
                "Spatial reference identified."
                if spatial_reference_valid
                else "Spatial reference is unknown."
            ),
            "Valid spatial reference",
            spatial_reference_name
        )
    )

    return checks, output_details

def validate_geometry(dataset_path):

    import os
    import uuid

    check_table = None
    cleanup_warnings = []

    # Preserve existing ArcGIS Pro environment
    previous_add_outputs = arcpy.env.addOutputsToMap

    try:

        # Prevent automatic map additions
        arcpy.env.addOutputsToMap = False

        scratch_gdb = arcpy.env.scratchGDB

        if not scratch_gdb or not arcpy.Exists(scratch_gdb):

            raise RuntimeError(
                "ArcGIS scratch geodatabase is unavailable."
            )

        table_name = (
            "GS_Geometry_Check_" + uuid.uuid4().hex[:8]
        )

        check_table = os.path.join(
            scratch_gdb,
            table_name
        )

        # Execute geometry validation
        arcpy.management.CheckGeometry(
            dataset_path,
            check_table,
            "ESRI"
        )

        # Independently retrieve issue count
        issue_count = int(
            arcpy.management.GetCount(check_table)[0]
        )

        geometry_status = (
            "PASS" if issue_count == 0 else "FAIL"
        )

        geometry_message = (
            "No geometry problems detected."
            if issue_count == 0
            else "Geometry problems were detected."
        )

    except Exception as error:

        geometry_status = "NOT_RUN"

        geometry_message = (
            "Geometry validation could not be completed: {}".format(
                error
            )
        )

        issue_count = None

    finally:

        # ---------------------------------------------
        # 1. REMOVE TEMPORARY TABLE REFERENCES
        # ---------------------------------------------

        if check_table:

            try:

                aprx = arcpy.mp.ArcGISProject("CURRENT")

                for map_obj in aprx.listMaps():

                    for table in map_obj.listTables():

                        if table.name == table_name:

                            map_obj.removeTable(table)

                            print(
                                "Removed temporary table reference: {}".format(
                                    table.name
                                )
                            )

            except Exception as cleanup_error:

                cleanup_warnings.append(
                    "Map reference cleanup failed: {}".format(
                        cleanup_error
                    )
                )

            # -----------------------------------------
            # 2. DELETE PHYSICAL TEMPORARY DATASET
            # -----------------------------------------

            try:

                if arcpy.Exists(check_table):

                    arcpy.management.Delete(check_table)

                    print(
                        "Deleted temporary geometry table: {}".format(
                            table_name
                        )
                    )

            except Exception as cleanup_error:

                cleanup_warnings.append(
                    "Temporary dataset cleanup failed: {}".format(
                        cleanup_error
                    )
                )

        # ---------------------------------------------
        # 3. RESTORE ORIGINAL ENVIRONMENT
        # ---------------------------------------------

        arcpy.env.addOutputsToMap = previous_add_outputs

    if cleanup_warnings:

        geometry_message += " Cleanup warning: " + "; ".join(
            cleanup_warnings
        )

    result = create_check(
        check_name="geometry_validity",
        status=geometry_status,
        message=geometry_message,
        expected=0,
        actual=issue_count
    )

    if cleanup_warnings and geometry_status == "PASS":

        result["cleanup_status"] = "WARNING"

    return result