
"""
GeoSentinel AI
GIS Inspector v0.3
Spatial Data Quality Validator

Runs inside the ArcGIS Pro Python environment.

Capabilities:
1. Inspect ArcGIS Pro project and layers.
2. Validate coordinate systems.
3. Identify geographic coordinate systems.
4. Check empty feature layers.
5. Validate feature geometry.
6. Inspect raster resolution.
7. Detect broken data sources.
8. Identify overlapping spatial extents.
9. Generate structured JSON validation reports.
"""

import arcpy
import json
import os
import uuid

from collections import defaultdict


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

RUN_GEOMETRY_VALIDATION = True

# Geometry validation can take time on large datasets.
# Set this to False when inspecting very large datasets.


# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_spatial_reference(desc):

    try:
        sr = desc.spatialReference

        return {
            "name": sr.name,
            "factory_code": sr.factoryCode,
            "type": sr.type,
            "linear_unit": getattr(sr, "linearUnitName", None),
            "angular_unit": getattr(sr, "angularUnitName", None)
        }

    except Exception:
        return None


def get_extent(desc):

    try:
        extent = desc.extent

        return {
            "xmin": extent.XMin,
            "ymin": extent.YMin,
            "xmax": extent.XMax,
            "ymax": extent.YMax
        }

    except Exception:
        return None


def get_layer_source(layer):

    try:
        if layer.supports("DATASOURCE"):
            return layer.dataSource
    except Exception:
        pass

    return None


# ---------------------------------------------------------
# VALIDATION HELPERS
# ---------------------------------------------------------

def add_issue(issues, severity, code, message, recommendation):

    issues.append({
        "severity": severity,
        "code": code,
        "message": message,
        "recommendation": recommendation
    })


def validate_spatial_reference(desc, issues):

    sr = desc.spatialReference

    if sr is None or sr.name == "Unknown" or sr.factoryCode == 0:

        add_issue(
            issues,
            "ERROR",
            "UNKNOWN_COORDINATE_SYSTEM",
            "Dataset has an undefined coordinate system.",
            "Define the correct coordinate system using authoritative "
            "source information. Do not guess or assign one arbitrarily."
        )

        return None

    if sr.type == "Geographic":

        add_issue(
            issues,
            "WARNING",
            "GEOGRAPHIC_COORDINATE_SYSTEM",
            "Dataset uses a geographic coordinate system.",
            "Evaluate whether projection into an appropriate projected "
            "coordinate system is necessary for distance, area, buffer, "
            "or other measurement-based analysis."
        )

    return {
        "name": sr.name,
        "factory_code": sr.factoryCode,
        "type": sr.type,
        "linear_unit": getattr(sr, "linearUnitName", None),
        "angular_unit": getattr(sr, "angularUnitName", None)
    }


def validate_extent(desc, issues):

    extent = get_extent(desc)

    if extent is None:

        add_issue(
            issues,
            "WARNING",
            "EXTENT_UNAVAILABLE",
            "Could not retrieve the dataset extent.",
            "Check the data source and dataset properties."
        )

        return None

    if (
        extent["xmin"] > extent["xmax"]
        or extent["ymin"] > extent["ymax"]
    ):

        add_issue(
            issues,
            "ERROR",
            "INVALID_EXTENT",
            "Dataset has an invalid spatial extent.",
            "Inspect the dataset geometry or raster properties."
        )

    return extent


def validate_feature_count(layer, issues):

    try:

        count = int(arcpy.management.GetCount(layer)[0])

        if count == 0:

            add_issue(
                issues,
                "WARNING",
                "EMPTY_FEATURE_LAYER",
                "Feature layer contains zero records.",
                "Verify that the dataset contains the expected features "
                "and that any applied definition query is correct."
            )

        return count

    except Exception as error:

        add_issue(
            issues,
            "ERROR",
            "FEATURE_COUNT_FAILED",
            str(error),
            "Check dataset accessibility and permissions."
        )

        return None



def validate_geometry(layer, issues):

    if not RUN_GEOMETRY_VALIDATION:
        return {
            "status": "SKIPPED",
            "problem_count": None
        }

    output_table = None

    try:

        # Use ArcGIS Pro scratch geodatabase
        scratch_gdb = arcpy.env.scratchGDB

        if not scratch_gdb or not arcpy.Exists(scratch_gdb):
            raise RuntimeError(
                "ArcGIS scratch geodatabase is unavailable."
            )

        output_table = os.path.join(
            scratch_gdb,
            "GS_Geometry_" + uuid.uuid4().hex[:8]
        )

        # Use the underlying dataset path
        input_dataset = layer.dataSource

        # Run geometry validation
        arcpy.management.CheckGeometry(
            input_dataset,
            output_table,
            "ESRI"
        )

        # Confirm output was created
        if not arcpy.Exists(output_table):

            raise RuntimeError(
                "CheckGeometry completed without creating "
                "the expected output table. "
                + arcpy.GetMessages()
            )

        # Count geometry problems
        problem_count = int(
            arcpy.management.GetCount(output_table)[0]
        )

        if problem_count > 0:

            add_issue(
                issues,
                "WARNING",
                "GEOMETRY_PROBLEMS_FOUND",
                "{} geometry problem(s) detected.".format(
                    problem_count
                ),
                "Review the Check Geometry output. "
                "Repair geometry only after reviewing "
                "the original data and creating a backup."
            )

            return {
                "status": "ISSUES_FOUND",
                "problem_count": problem_count
            }

        return {
            "status": "VALID",
            "problem_count": 0
        }

    except Exception as error:

        add_issue(
            issues,
            "WARNING",
            "GEOMETRY_VALIDATION_FAILED",
            str(error),
            "Check the input dataset, Check Geometry tool "
            "messages, and scratch geodatabase permissions."
        )

        return {
            "status": "FAILED",
            "problem_count": None
        }

    finally:

        # Remove temporary output
        try:
            if output_table and arcpy.Exists(output_table):
                arcpy.management.Delete(output_table)
        except Exception:
            pass

def validate_raster(desc, issues):

    properties = {
        "width": getattr(desc, "width", None),
        "height": getattr(desc, "height", None),
        "band_count": getattr(desc, "bandCount", None),
        "pixel_type": getattr(desc, "pixelType", None),
        "cell_size_x": safe_float(
            getattr(desc, "meanCellWidth", None)
        ),
        "cell_size_y": safe_float(
            getattr(desc, "meanCellHeight", None)
        )
    }

    width = properties["width"]
    height = properties["height"]

    if width == 0 or height == 0:

        add_issue(
            issues,
            "ERROR",
            "INVALID_RASTER_DIMENSIONS",
            "Raster has zero width or height.",
            "Inspect the raster dataset and verify its source."
        )

    cell_x = properties["cell_size_x"]
    cell_y = properties["cell_size_y"]

    if (
        cell_x is not None and cell_x <= 0
    ) or (
        cell_y is not None and cell_y <= 0
    ):

        add_issue(
            issues,
            "ERROR",
            "INVALID_RASTER_CELL_SIZE",
            "Raster has a non-positive cell size.",
            "Check the raster properties and source dataset."
        )

    return properties


# ---------------------------------------------------------
# LAYER INSPECTION
# ---------------------------------------------------------

def inspect_layer(layer):

    info = {
        "name": layer.name,
        "long_name": layer.longName,
        "visible": layer.visible,
        "is_broken": layer.isBroken,
        "layer_type": "Unknown",
        "data_source": get_layer_source(layer),
        "issues": []
    }

    issues = info["issues"]

    if layer.isBroken:

        add_issue(
            issues,
            "ERROR",
            "BROKEN_DATA_SOURCE",
            "Layer data source is broken or unavailable.",
            "Repair the data source before using this layer."
        )

        info["validation_status"] = "ERROR"

        return info

    try:

        # ---------------------------------------------
        # GROUP LAYER
        # ---------------------------------------------

        if layer.isGroupLayer:

            info["layer_type"] = "Group"

            info["children"] = [
                inspect_layer(child)
                for child in layer.listLayers()
            ]

            child_statuses = [
                child.get("validation_status", "VALID")
                for child in info["children"]
            ]

            if "ERROR" in child_statuses:
                info["validation_status"] = "ERROR"

            elif "WARNING" in child_statuses:
                info["validation_status"] = "WARNING"

            else:
                info["validation_status"] = "VALID"

            return info

        # ---------------------------------------------
        # FEATURE LAYER
        # ---------------------------------------------

        if layer.isFeatureLayer:

            info["layer_type"] = "Feature"

            desc = arcpy.Describe(layer)

            info["geometry_type"] = desc.shapeType

            info["spatial_reference"] = (
                validate_spatial_reference(desc, issues)
            )

            info["extent"] = validate_extent(desc, issues)

            info["feature_count"] = validate_feature_count(
                layer,
                issues
            )

            info["fields"] = [
                {
                    "name": field.name,
                    "type": field.type
                }
                for field in arcpy.ListFields(layer)
            ]

            info["geometry_validation"] = validate_geometry(
                layer,
                issues
            )

        # ---------------------------------------------
        # RASTER LAYER
        # ---------------------------------------------

        elif layer.isRasterLayer:

            info["layer_type"] = "Raster"

            desc = arcpy.Describe(layer)

            info["spatial_reference"] = (
                validate_spatial_reference(desc, issues)
            )

            info["extent"] = validate_extent(desc, issues)

            info["raster_properties"] = validate_raster(
                desc,
                issues
            )

        # ---------------------------------------------
        # OTHER / SERVICE LAYER
        # ---------------------------------------------

        else:

            info["layer_type"] = "Other"

        source = info["data_source"]

        info["is_service_layer"] = bool(
            source and source.lower().startswith(
                ("http://", "https://")
            )
        )

    except Exception as error:

        add_issue(
            issues,
            "ERROR",
            "LAYER_INSPECTION_FAILED",
            str(error),
            "Inspect the layer manually in ArcGIS Pro."
        )

    # ---------------------------------------------
    # FINAL STATUS
    # ---------------------------------------------

    severities = [
        issue["severity"]
        for issue in issues
    ]

    if "ERROR" in severities:
        info["validation_status"] = "ERROR"

    elif "WARNING" in severities:
        info["validation_status"] = "WARNING"

    else:
        info["validation_status"] = "VALID"

    return info


# ---------------------------------------------------------
# MAP INSPECTION
# ---------------------------------------------------------

def inspect_map(map_obj):

    map_info = {
        "map_name": map_obj.name,
        "layers": []
    }

    for layer in map_obj.listLayers():

        map_info["layers"].append(
            inspect_layer(layer)
        )

    return map_info


# ---------------------------------------------------------
# SPATIAL EXTENT OVERLAP VALIDATION
# ---------------------------------------------------------

def collect_dataset_layers(layers, output):

    for layer in layers:

        if layer.get("children"):

            collect_dataset_layers(
                layer["children"],
                output
            )

        elif (
            layer.get("extent")
            and layer.get("spatial_reference")
        ):

            output.append(layer)


def extents_overlap(extent_a, extent_b):

    return not (
        extent_a["xmax"] < extent_b["xmin"]
        or extent_a["xmin"] > extent_b["xmax"]
        or extent_a["ymax"] < extent_b["ymin"]
        or extent_a["ymin"] > extent_b["ymax"]
    )


def validate_spatial_overlaps(maps):

    datasets = []

    for map_info in maps:

        collect_dataset_layers(
            map_info["layers"],
            datasets
        )

    results = []

    for index, layer_a in enumerate(datasets):

        for layer_b in datasets[index + 1:]:

            sr_a = layer_a["spatial_reference"]
            sr_b = layer_b["spatial_reference"]

            # Compare only when coordinate systems match.
            same_sr = (
                sr_a["factory_code"] == sr_b["factory_code"]
                and sr_a["name"] == sr_b["name"]
            )

            if not same_sr:
                continue

            overlap = extents_overlap(
                layer_a["extent"],
                layer_b["extent"]
            )

            results.append({
                "layer_a": layer_a["name"],
                "layer_b": layer_b["name"],
                "same_coordinate_system": True,
                "extent_overlap": overlap
            })

    return results


# ---------------------------------------------------------
# DUPLICATE DATA SOURCE DETECTION
# ---------------------------------------------------------

def find_duplicate_sources(maps):

    sources = defaultdict(list)

    def collect(layers):

        for layer in layers:

            source = layer.get("data_source")

            if source:

                normalized = os.path.normcase(
                    os.path.normpath(source)
                )

                sources[normalized].append(
                    layer["name"]
                )

            if layer.get("children"):

                collect(layer["children"])

    for map_info in maps:

        collect(map_info["layers"])

    duplicates = []

    for source, names in sources.items():

        if len(names) > 1:

            duplicates.append({
                "data_source": source,
                "referenced_by": names,
                "duplicate_layer_count": len(names)
            })

    return duplicates


# ---------------------------------------------------------
# VALIDATION SUMMARY
# ---------------------------------------------------------

def build_validation_summary(maps):

    all_layers = []

    def collect(layers):

        for layer in layers:

            if layer.get("children"):
                collect(layer["children"])

            elif layer.get("layer_type") != "Other":
                all_layers.append(layer)

    for map_info in maps:

        collect(map_info["layers"])

    summary = {
        "total_layers": len(all_layers),
        "valid_layers": 0,
        "warning_layers": 0,
        "error_layers": 0,
        "total_warnings": 0,
        "total_errors": 0
    }

    for layer in all_layers:

        status = layer.get("validation_status")

        if status == "VALID":
            summary["valid_layers"] += 1

        elif status == "WARNING":
            summary["warning_layers"] += 1

        elif status == "ERROR":
            summary["error_layers"] += 1

        for issue in layer.get("issues", []):

            if issue["severity"] == "WARNING":
                summary["total_warnings"] += 1

            elif issue["severity"] == "ERROR":
                summary["total_errors"] += 1

    return summary


# ---------------------------------------------------------
# MAIN PROJECT INSPECTOR
# ---------------------------------------------------------

def inspect_project():

    aprx = arcpy.mp.ArcGISProject("CURRENT")

    maps = [
        inspect_map(map_obj)
        for map_obj in aprx.listMaps()
    ]

    summary = build_validation_summary(maps)

    return {

        "application": "GeoSentinel AI",

        "inspector_version": "0.3",

        "project_name": os.path.basename(
            aprx.filePath
        ),

        "project_path": aprx.filePath,

        "arcgis_pro_version": (
            arcpy.GetInstallInfo()["Version"]
        ),

        "validation_summary": summary,

        "maps": maps,

        "spatial_extent_analysis": (
            validate_spatial_overlaps(maps)
        ),

        "duplicate_sources": (
            find_duplicate_sources(maps)
        )
    }


# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------

def main():

    result = inspect_project()

    print(
        "\n========== GEOSENTINEL GIS INSPECTOR v0.3 ==========\n"
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