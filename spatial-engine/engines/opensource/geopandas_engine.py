"""
GeoSentinel AI
Open-Source GIS Execution Engine
Version: 1.0.0

Initial capabilities:
- Buffer
- Dissolve ALL / NONE

Dependencies:
- GeoPandas
- Shapely
- PyProj
- Pyogrio

No ArcGIS Pro dependency.
"""

import os
import re
import tempfile

from pathlib import Path

import geopandas as gpd
from pyproj import CRS

from engines.base import (
    BaseGISExecutionEngine,
    ExecutionRequest,
    ExecutionResult,
)


class GeoPandasEngine(BaseGISExecutionEngine):

    engine_name = "opensource"
    engine_version = "1.0.0"

    SUPPORTED_OPERATIONS = [
        "buffer",
    ]

    DISTANCE_PATTERN = re.compile(
        r"^\s*(\d+(?:\.\d+)?)\s*"
        r"(meters?|kilometers?|feet|foot|miles?|yards?)\s*$",
        re.IGNORECASE,
    )

    UNIT_TO_METERS = {
        "meter": 1.0,
        "meters": 1.0,
        "kilometer": 1000.0,
        "kilometers": 1000.0,
        "foot": 0.3048,
        "feet": 0.3048,
        "mile": 1609.344,
        "miles": 1609.344,
        "yard": 0.9144,
        "yards": 0.9144,
    }

    # -----------------------------------------------------
    # ENGINE AVAILABILITY
    # -----------------------------------------------------

    def is_available(self) -> bool:

        try:
            import geopandas
            import shapely
            import pyproj
            import pyogrio

            return True

        except ImportError:
            return False

    # -----------------------------------------------------
    # CAPABILITIES
    # -----------------------------------------------------

    def supported_operations(self) -> list[str]:

        return list(self.SUPPORTED_OPERATIONS)

    # -----------------------------------------------------
    # DISTANCE VALIDATION
    # -----------------------------------------------------

    def parse_distance(self, distance: str) -> float:

        if not isinstance(distance, str):
            raise ValueError("Buffer distance must be a string.")

        match = self.DISTANCE_PATTERN.fullmatch(distance)

        if not match:
            raise ValueError(
                "Invalid distance. Example: 500 Meters."
            )

        value = float(match.group(1))
        unit = match.group(2).lower()

        if value <= 0:
            raise ValueError(
                "Buffer distance must be greater than zero."
            )

        normalized_unit = unit.rstrip("s")

        if normalized_unit == "feet":
            normalized_unit = "foot"

        return value * self.UNIT_TO_METERS[unit.lower()]

    # -----------------------------------------------------
    # BUFFER OPERATION
    # -----------------------------------------------------

    def execute_buffer(
        self,
        request: ExecutionRequest
    ) -> dict:

        inputs = request.inputs
        parameters = request.parameters

        input_path = inputs.get("input_features")

        if not isinstance(input_path, str) or not input_path.strip():
            raise ValueError("Input feature dataset path is missing.")

        input_path = Path(input_path).resolve()

        if not input_path.is_file():
            raise FileNotFoundError(
                f"Input dataset does not exist: {input_path}"
            )

        distance = parameters.get("distance")

        distance_meters = self.parse_distance(distance)

        dissolve_option = parameters.get(
            "dissolve_option",
            "NONE"
        )

        if dissolve_option not in ("NONE", "ALL"):
            raise ValueError(
                "Dissolve option must be NONE or ALL."
            )

        # Read input dataset.
        gdf = gpd.read_file(input_path, engine="pyogrio")

        if gdf.empty:
            raise ValueError("Input dataset contains no features.")

        if gdf.crs is None:
            raise ValueError(
                "Input dataset has no CRS. "
                "Assign a valid CRS before buffering."
            )

        source_crs = CRS.from_user_input(gdf.crs)

        # Determine the analysis CRS.
        analysis_crs_value = parameters.get("analysis_crs")

        if analysis_crs_value:
            analysis_crs = CRS.from_user_input(
                analysis_crs_value
            )

            if not analysis_crs.is_projected:
                raise ValueError(
                    "Analysis CRS must be projected."
                )

        elif source_crs.is_projected:
            analysis_crs = source_crs

        else:
            raise ValueError(
                "Input CRS is geographic. Supply an explicit "
                "projected analysis_crs, such as an appropriate "
                "UTM or local projected CRS."
            )

        # Reproject before distance-based operations.
        analysis_gdf = gdf.to_crs(analysis_crs)

        # Convert metres into the analysis CRS linear units.
        axis_info = analysis_crs.axis_info

        if not axis_info:
            raise ValueError(
                "Unable to determine analysis CRS units."
            )

        unit_to_meters = axis_info[0].unit_conversion_factor

        if not unit_to_meters or unit_to_meters <= 0:
            raise ValueError(
                "Invalid analysis CRS linear unit."
            )

        distance_in_crs_units = (
            distance_meters / unit_to_meters
        )

        # Perform buffer.
        buffered = analysis_gdf.copy()

        buffered.geometry = analysis_gdf.geometry.buffer(
            distance_in_crs_units
        )

        if buffered.geometry.is_empty.any():
            raise ValueError(
                "Buffer operation produced empty geometries."
            )

        # Dissolve behavior.
        if dissolve_option == "ALL":

            buffered = buffered.dissolve()

            buffered = buffered.reset_index(drop=True)

        # Return output to source CRS.
        output_crs_value = parameters.get("output_crs")

        output_crs = (
            CRS.from_user_input(output_crs_value)
            if output_crs_value
            else source_crs
        )

        buffered = buffered.to_crs(output_crs)

        if not buffered.geometry.is_valid.all():
            raise ValueError(
                "Buffer output contains invalid geometries."
            )

        return {
            "gdf": buffered,
            "input_feature_count": len(gdf),
            "output_feature_count": len(buffered),
            "buffer_distance": distance,
            "buffer_distance_meters": distance_meters,
            "dissolve_option": dissolve_option,
            "analysis_crs": analysis_crs.to_string(),
            "output_crs": output_crs.to_string(),
            "geometry_type": list(
                buffered.geom_type.unique()
            ),
        }

    # -----------------------------------------------------
    # OUTPUT WRITER
    # -----------------------------------------------------

    def write_output(
        self,
        gdf: gpd.GeoDataFrame,
        output_path: str,
    ) -> str:

        destination = Path(output_path).resolve()

        if destination.suffix.lower() != ".gpkg":
            raise ValueError(
                "Open-source engine currently requires "
                "a .gpkg output."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if destination.exists():
            raise FileExistsError(
                f"Output already exists: {destination}"
            )

        # Create temporary GeoPackage in the same directory.
        # os.link publishes it without overwriting an existing file.
        fd, temp_path = tempfile.mkstemp(
            prefix="geosentinel_",
            suffix=".gpkg",
            dir=str(destination.parent),
        )

        os.close(fd)
        os.remove(temp_path)

        try:

            layer_name = destination.stem

            gdf.to_file(
                temp_path,
                layer=layer_name,
                driver="GPKG",
                engine="pyogrio",
                index=False,
            )

            if not os.path.isfile(temp_path):
                raise RuntimeError(
                    "GeoPackage output was not created."
                )

            # Atomic, no-overwrite publication on the same filesystem.
            os.link(temp_path, destination)

            return str(destination)

        finally:

            if os.path.exists(temp_path):
                os.remove(temp_path)

    # -----------------------------------------------------
    # MAIN EXECUTION INTERFACE
    # -----------------------------------------------------

    def execute(
        self,
        request: ExecutionRequest
    ) -> ExecutionResult:

        try:

            request.validate()

            if request.engine != self.engine_name:
                raise ValueError(
                    "Execution request targets a different engine."
                )

            if not self.is_available():
                raise RuntimeError(
                    "GeoPandas engine dependencies are unavailable."
                )

            if request.operation_id not in self.supported_operations():
                raise ValueError(
                    "Unsupported operation: "
                    + request.operation_id
                )

            if request.operation_id == "buffer":

                operation_result = self.execute_buffer(request)

                output_path = self.write_output(
                    operation_result.pop("gdf"),
                    request.output_path,
                )

                return ExecutionResult(
                    job_id=request.job_id,
                    workflow_id=request.workflow_id,
                    approval_id=request.approval_id,
                    engine=self.engine_name,
                    engine_version=self.engine_version,
                    operation_id=request.operation_id,
                    status="SUCCESS",
                    message="Buffer operation completed successfully.",
                    output_path=output_path,
                    details=operation_result,
                )

        except Exception as error:

            return ExecutionResult(
                job_id=request.job_id,
                workflow_id=request.workflow_id,
                approval_id=request.approval_id,
                engine=self.engine_name,
                engine_version=self.engine_version,
                operation_id=request.operation_id,
                status="FAILED",
                message=str(error),
            )