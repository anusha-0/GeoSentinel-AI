"""
GeoSentinel AI
Custom GIS MCP Server v0.5

Exposes registered GIS operations through
the Model Context Protocol.

Current capabilities:
1. List registered GIS operations.
2. Retrieve operation specifications.
3. Validate GIS operation requests.

IMPORTANT:
This version does not execute ArcPy tools.
GIS execution will be implemented through
a separate ArcGIS Pro execution component.
"""

import json
import sys

from pathlib import Path

from mcp.server import MCPServer


# ---------------------------------------------------------
# PROJECT PATHS
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SPATIAL_ENGINE_DIR = PROJECT_ROOT / "spatial-engine"

if str(SPATIAL_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(SPATIAL_ENGINE_DIR))


from operation_registry import OperationRegistry


# ---------------------------------------------------------
# INITIALIZE SERVER
# ---------------------------------------------------------

mcp = MCPServer(
    "GeoSentinel GIS MCP Server",
    version="0.5.0"
)
registry = OperationRegistry()


# ---------------------------------------------------------
# TOOL 1: SERVER INFORMATION
# ---------------------------------------------------------

@mcp.tool()
def get_server_info() -> dict:
    """
    Returns information about the GeoSentinel GIS MCP server.

    This tool does not execute GIS operations.
    """

    return {
        "application": "GeoSentinel AI",
        "server_name": "GeoSentinel GIS MCP Server",
        "server_version": "0.5.0",
        "registry_version": registry.registry["version"],
        "execution_enabled": False,
        "capabilities": [
            "list_gis_operations",
            "get_gis_operation",
            "validate_gis_request"
        ],
        "execution_engine": "Not connected"
    }


# ---------------------------------------------------------
# TOOL 2: LIST GIS OPERATIONS
# ---------------------------------------------------------

@mcp.tool()
def list_gis_operations(category: str = "") -> dict:
    """
    Lists available GIS operations registered in GeoSentinel.

    Optionally filter operations by category.

    Examples:
    vector_analysis
    terrain_analysis
    raster_analysis
    coordinate_transformation
    """

    operations = registry.list_operations()

    if category:

        operations = [
            operation
            for operation in operations
            if operation["category"] == category
        ]

    return {
        "total_operations": len(operations),
        "category_filter": category or "all",
        "operations": operations
    }


# ---------------------------------------------------------
# TOOL 3: GET OPERATION DETAILS
# ---------------------------------------------------------

@mcp.tool()
def get_gis_operation(operation_id: str) -> dict:
    """
    Returns the complete specification of a registered GIS operation.

    Example operation IDs:
    buffer
    clip
    spatial_join
    slope
    aspect
    hillshade
    zonal_statistics
    """

    try:

        operation = registry.get_operation(operation_id)

        return {
            "success": True,
            "operation": operation
        }

    except ValueError as error:

        return {
            "success": False,
            "error": str(error)
        }


# ---------------------------------------------------------
# TOOL 4: VALIDATE GIS REQUEST
# ---------------------------------------------------------

@mcp.tool()
def validate_gis_request(
    operation_id: str,
    inputs_json: str,
    parameters_json: str
) -> dict:
    """
    Validates the structure of a GIS operation request.

    inputs_json and parameters_json must be JSON objects
    encoded as strings.

    This performs registry-level validation only.
    It does not inspect live ArcGIS Pro layers,
    check ArcGIS licenses, or execute ArcPy tools.
    """

    try:

        inputs = json.loads(inputs_json)

        parameters = json.loads(parameters_json)

        if not isinstance(inputs, dict):

            return {
                "valid": False,
                "error": "Inputs must be a JSON object."
            }

        if not isinstance(parameters, dict):

            return {
                "valid": False,
                "error": "Parameters must be a JSON object."
            }

        result = registry.validate_request(
            operation_id=operation_id,
            inputs=inputs,
            parameters=parameters
        )

        return {
            "application": "GeoSentinel AI",
            "validation_stage": "Registry-level",
            "result": result,
            "execution_enabled": False,
            "execution_performed": False
        }

    except json.JSONDecodeError as error:

        return {
            "valid": False,
            "error": "Invalid JSON input: {}".format(error)
        }

    except ValueError as error:

        return {
            "valid": False,
            "error": str(error)
        }


# ---------------------------------------------------------
# SERVER ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":

    mcp.run(transport="stdio")
