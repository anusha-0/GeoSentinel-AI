"""
GeoSentinel AI
GIS Operation Registry v0.4

Loads approved GIS operation definitions
and validates requests from future AI agents.

This module does NOT execute ArcPy tools.
"""

import json
import os


REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__),
    "operation_registry.json"
)


class OperationRegistry:

    def __init__(self, registry_path=REGISTRY_PATH):

        self.registry_path = registry_path
        self.registry = self._load_registry()

        self.operations = {
            operation["id"]: operation
            for operation in self.registry["operations"]
        }

    def _load_registry(self):

        if not os.path.exists(self.registry_path):
            raise FileNotFoundError(
                "Operation registry not found: "
                + self.registry_path
            )

        with open(
            self.registry_path,
            "r",
            encoding="utf-8"
        ) as file:

            registry = json.load(file)

        if "operations" not in registry:
            raise ValueError(
                "Invalid registry: operations section missing."
            )

        return registry

    def list_operations(self):

        return [
            {
                "id": operation["id"],
                "name": operation["name"],
                "category": operation["category"],
                "description": operation["description"],
                "risk_level": operation["risk_level"]
            }
            for operation in self.operations.values()
        ]

    def get_operation(self, operation_id):

        operation = self.operations.get(operation_id)

        if operation is None:
            raise ValueError(
                "Operation is not registered: "
                + operation_id
            )

        return operation

    def validate_request(
        self,
        operation_id,
        inputs,
        parameters
    ):

        operation = self.get_operation(operation_id)

        errors = []

        # Validate required inputs
        for input_definition in operation["inputs"]:

            name = input_definition["name"]

            if (
                input_definition["required"]
                and name not in inputs
            ):

                errors.append(
                    "Missing required input: " + name
                )

        # Validate required parameters
        for parameter in operation["parameters"]:

            name = parameter["name"]

            if (
                parameter["required"]
                and name not in parameters
            ):

                errors.append(
                    "Missing required parameter: " + name
                )

            if name in parameters:

                allowed_values = parameter.get(
                    "allowed_values"
                )

                if (
                    allowed_values
                    and parameters[name] not in allowed_values
                ):

                    errors.append(
                        "Invalid value for {}. Allowed values: {}".format(
                            name,
                            allowed_values
                        )
                    )

                expected_type = parameter["type"]
                value = parameters[name]

                if expected_type == "number":

                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                    ):

                        errors.append(
                            "{} must be a number.".format(name)
                        )

        return {

            "operation_id": operation_id,

            "valid": len(errors) == 0,

            "errors": errors,

            "approval_required": operation[
                "approval_required"
            ],

            "execution_enabled": self.registry.get(
                "execution_enabled",
                False
            )
        }


# --------------------------------------------------
# LOCAL TEST
# --------------------------------------------------

def main():

    registry = OperationRegistry()

    print("\n========== GEOSENTINEL OPERATION REGISTRY ==========\n")

    print("Registry version:", registry.registry["version"])

    print("\nRegistered operations:\n")

    for operation in registry.list_operations():

        print(
            "{} | {} | {}".format(
                operation["id"],
                operation["name"],
                operation["risk_level"]
            )
        )

    print("\n========== TEST REQUEST ==========\n")

    test_result = registry.validate_request(

        operation_id="buffer",

        inputs={
            "input_features": "GS_Test_Settlements"
        },

        parameters={
            "distance": "500 Meters",
            "dissolve_option": "ALL"
        }
    )

    print(json.dumps(test_result, indent=4))

    print("\n========== REGISTRY TEST COMPLETED ==========\n")


if __name__ == "__main__":
    main()