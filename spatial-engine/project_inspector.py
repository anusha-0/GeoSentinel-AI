"""
GeoSentinel AI
GIS Project Inspector v0.2

Enhanced ArcGIS Pro project inspection.
"""

import arcpy
import json
import os
from collections import defaultdict


def get_spatial_reference(desc):

    try:
        sr = desc.spatialReference

        return {
            "name": sr.name,
            "factory_code": sr.factoryCode
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


def inspect_layer(layer):

    info = {
        "name": layer.name,
        "long_name": layer.longName,
        "visible": layer.visible,
        "is_broken": layer.isBroken,
        "layer_type": "Unknown",
        "data_source": None
    }

    try:

        if layer.supports("DATASOURCE"):
            info["data_source"] = layer.dataSource

        if layer.isGroupLayer:

            info["layer_type"] = "Group"

            info["children"] = [
                inspect_layer(child)
                for child in layer.listLayers()
            ]

            return info

        if layer.isFeatureLayer:

            info["layer_type"] = "Feature"

            desc = arcpy.Describe(layer)

            info["geometry_type"] = desc.shapeType

            info["spatial_reference"] = (
                get_spatial_reference(desc)
            )

            info["extent"] = get_extent(desc)

            info["feature_count"] = int(
                arcpy.management.GetCount(layer)[0]
            )

            info["fields"] = [
                {
                    "name": field.name,
                    "type": field.type
                }
                for field in arcpy.ListFields(layer)
            ]

        elif layer.isRasterLayer:

            info["layer_type"] = "Raster"

            desc = arcpy.Describe(layer)

            info["spatial_reference"] = (
                get_spatial_reference(desc)
            )

            info["extent"] = get_extent(desc)

            info["raster_properties"] = {
                "width": getattr(desc, "width", None),
                "height": getattr(desc, "height", None),
                "band_count": getattr(desc, "bandCount", None),
                "pixel_type": getattr(desc, "pixelType", None),
                "cell_size_x": getattr(desc, "meanCellWidth", None),
                "cell_size_y": getattr(desc, "meanCellHeight", None)
            }

        else:

            info["layer_type"] = "Other"

        source = info["data_source"]

        info["is_service_layer"] = bool(
            source and source.lower().startswith(
                ("http://", "https://")
            )
        )

    except Exception as error:

        info["inspection_error"] = str(error)

    return info


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


def find_duplicate_sources(maps):

    sources = defaultdict(list)

    def collect_layers(layers):

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
                collect_layers(layer["children"])

    for map_info in maps:
        collect_layers(map_info["layers"])

    duplicates = []

    for source, layer_names in sources.items():

        if len(layer_names) > 1:

            duplicates.append({
                "data_source": source,
                "referenced_by": layer_names,
                "duplicate_layer_count": len(layer_names)
            })

    return duplicates


def inspect_project():

    aprx = arcpy.mp.ArcGISProject("CURRENT")

    maps = []

    for map_obj in aprx.listMaps():

        maps.append(
            inspect_map(map_obj)
        )

    result = {
        "project_name": os.path.basename(aprx.filePath),
        "project_path": aprx.filePath,
        "arcgis_pro_version": arcpy.GetInstallInfo()["Version"],
        "maps": maps,
        "duplicate_sources": find_duplicate_sources(maps)
    }

    return result


def main():

    result = inspect_project()

    print("\n========== GEOSENTINEL GIS INSPECTOR v0.2 ==========\n")

    print(json.dumps(result, indent=4))

    print("\n========== INSPECTION COMPLETED ==========\n")


if __name__ == "__main__":
    main()