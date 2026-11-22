"""
GeoSentinel AI
GIS Verification Rules v0.8.5

Independent inspection of ArcGIS datasets.
Runs inside the ArcGIS Pro Python environment.
"""

import os
import uuid
import arcpy


TEMP_TABLE_PREFIX = "GS_Geometry_Check_"


def create_check(check_name, status, message, expected=None, actual=None):
    return {
        "check": check_name,
        "status": status,
        "message": message,
        "expected": expected,
        "actual": actual,
    }


def inspect_feature_class(dataset_path, expected_geometry_type=None):
    checks = []
    output_details = {}

    if not arcpy.Exists(dataset_path):
        checks.append(create_check(
            "output_exists", "FAIL", "Output dataset does not exist.", True, False
        ))
        return checks, output_details

    checks.append(create_check(
        "output_exists", "PASS", "Output dataset exists.", True, True
    ))

    try:
        description = arcpy.Describe(dataset_path)
        geometry_type = description.shapeType
        spatial_reference = description.spatialReference

        output_details["dataset"] = description.name
        output_details["geometry_type"] = geometry_type
        output_details["spatial_reference"] = {
            "name": spatial_reference.name,
            "factory_code": spatial_reference.factoryCode,
        }
    except Exception as error:
        checks.append(create_check(
            "dataset_description", "FAIL",
            "Unable to describe output dataset: {}".format(error)
        ))
        return checks, output_details

    if expected_geometry_type:
        geometry_matches = geometry_type.lower() == expected_geometry_type.lower()
        checks.append(create_check(
            "geometry_type",
            "PASS" if geometry_matches else "FAIL",
            "Output geometry type is correct." if geometry_matches
            else "Output geometry type does not match.",
            expected_geometry_type,
            geometry_type,
        ))

    try:
        feature_count = int(arcpy.management.GetCount(dataset_path)[0])
        output_details["feature_count"] = feature_count
        checks.append(create_check(
            "feature_count",
            "PASS" if feature_count > 0 else "FAIL",
            "Output contains features." if feature_count > 0
            else "Output dataset is empty.",
            "> 0",
            feature_count,
        ))
    except Exception as error:
        checks.append(create_check(
            "feature_count", "FAIL",
            "Unable to retrieve feature count: {}".format(error)
        ))

    spatial_reference_name = spatial_reference.name
    spatial_reference_valid = spatial_reference_name not in (None, "", "Unknown")
    checks.append(create_check(
        "spatial_reference",
        "PASS" if spatial_reference_valid else "FAIL",
        "Spatial reference identified." if spatial_reference_valid
        else "Spatial reference is unknown.",
        "Valid spatial reference",
        spatial_reference_name,
    ))

    return checks, output_details


def _normalized_path(path):
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.normpath(path))
    except Exception:
        return str(path).lower()


def _remove_map_references(dataset_path=None, table_name=None):
    """
    Remove references from every map in the current ArcGIS Pro project.
    Match both table name and data source because ArcGIS may expose a
    broken table reference differently after its backing dataset is deleted.
    """
    warnings = []
    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        target_path = _normalized_path(dataset_path)

        for map_obj in aprx.listMaps():
            # listTables() returns a snapshot; collect matches before removal.
            matches = []
            for table in map_obj.listTables():
                try:
                    name_matches = bool(table_name) and table.name == table_name
                except Exception:
                    name_matches = False

                try:
                    source_matches = bool(target_path) and (
                        _normalized_path(table.dataSource) == target_path
                    )
                except Exception:
                    source_matches = False

                if name_matches or source_matches:
                    matches.append(table)

            for table in matches:
                try:
                    map_obj.removeTable(table)
                    print("Removed temporary table reference: {}".format(table.name))
                except Exception as error:
                    warnings.append(
                        "Could not remove table reference '{}': {}".format(
                            table_name or "unknown", error
                        )
                    )
    except Exception as error:
        warnings.append("Could not inspect ArcGIS Pro map references: {}".format(error))

    return warnings


def cleanup_stale_geometry_tables(scratch_gdb=None):
    """
    Remove only GeoSentinel's own diagnostic tables from scratch.gdb.
    This also cleans up orphan tables left by earlier verifier runs.
    """
    warnings = []
    if not scratch_gdb or not arcpy.Exists(scratch_gdb):
        return warnings

    previous_workspace = arcpy.env.workspace
    try:
        arcpy.env.workspace = scratch_gdb
        names = arcpy.ListTables(TEMP_TABLE_PREFIX + "*") or []

        for name in names:
            path = os.path.join(scratch_gdb, name)

            # Remove map references before deleting the physical table.
            warnings.extend(_remove_map_references(path, name))

            try:
                if arcpy.Exists(path):
                    arcpy.management.Delete(path)
                    print("Deleted stale GeoSentinel geometry table: {}".format(name))
            except Exception as error:
                warnings.append(
                    "Could not delete stale geometry table '{}': {}".format(name, error)
                )

            # A second pass removes any reference ArcGIS recreated/retained.
            warnings.extend(_remove_map_references(path, name))
    finally:
        arcpy.env.workspace = previous_workspace

    return warnings


def validate_geometry(dataset_path):
    """
    Run CheckGeometry and guarantee cleanup of its temporary output.

    The diagnostic table is created in scratch.gdb, removed from all maps,
    deleted from disk, and checked again for stale references. The original
    ArcPy environment settings are restored even if validation or cleanup fails.
    """
    check_table = None
    table_name = None
    issue_count = None
    cleanup_warnings = []
    geometry_status = "NOT_RUN"
    geometry_message = "Geometry validation was not completed."

    previous_add_outputs = arcpy.env.addOutputsToMap
    previous_workspace = arcpy.env.workspace
    scratch_gdb = arcpy.env.scratchGDB

    try:
        # Prevent geoprocessing outputs from being automatically added to maps.
        arcpy.env.addOutputsToMap = False

        if not scratch_gdb or not arcpy.Exists(scratch_gdb):
            raise RuntimeError("ArcGIS scratch geodatabase is unavailable.")

        # Clean leftovers from previous interrupted/older runs first.
        cleanup_warnings.extend(cleanup_stale_geometry_tables(scratch_gdb))

        table_name = TEMP_TABLE_PREFIX + uuid.uuid4().hex[:10]
        check_table = os.path.join(scratch_gdb, table_name)

        arcpy.management.CheckGeometry(dataset_path, check_table, "ESRI")
        issue_count = int(arcpy.management.GetCount(check_table)[0])

        geometry_status = "PASS" if issue_count == 0 else "FAIL"
        geometry_message = (
            "No geometry problems detected."
            if issue_count == 0
            else "Geometry problems were detected."
        )

    except Exception as error:
        geometry_status = "NOT_RUN"
        geometry_message = "Geometry validation could not be completed: {}".format(error)
        issue_count = None

    finally:
        # Remove the exact current output reference before deleting the dataset.
        if check_table:
            cleanup_warnings.extend(_remove_map_references(check_table, table_name))

            try:
                if arcpy.Exists(check_table):
                    arcpy.management.Delete(check_table)
                    print("Deleted temporary geometry table: {}".format(table_name))
            except Exception as error:
                cleanup_warnings.append(
                    "Temporary dataset cleanup failed for '{}': {}".format(
                        table_name, error
                    )
                )

            # Delete any remaining diagnostic tables from previous runs, then
            # remove map references once more to catch broken/orphan references.
            cleanup_warnings.extend(cleanup_stale_geometry_tables(scratch_gdb))
            cleanup_warnings.extend(_remove_map_references(check_table, table_name))

        # Restore both environments regardless of cleanup outcome.
        try:
            arcpy.env.workspace = previous_workspace
        finally:
            arcpy.env.addOutputsToMap = previous_add_outputs

    if cleanup_warnings:
        geometry_message += " Cleanup warning: " + "; ".join(cleanup_warnings)

    result = create_check(
        check_name="geometry_validity",
        status=geometry_status,
        message=geometry_message,
        expected=0,
        actual=issue_count,
    )

    if cleanup_warnings:
        result["cleanup_status"] = "WARNING"

    return result
