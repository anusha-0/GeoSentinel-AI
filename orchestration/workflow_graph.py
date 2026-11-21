import uuid
from typing import Any, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from orchestration.workflow_state import GeoSentinelState
from agents.planning_agent import GISPlanningAgent
from agents.workflow_validator import WorkflowValidator


class GeoSentinelWorkflowEngine:
    """
    GeoSentinel AI - LangGraph Workflow Engine.

    Workflow:
        Planning
            |
        Input Resolution
            |
        Validation
            |
        Human Approval
            |
        Execution Handoff

    ArcPy execution is handled separately by the
    ArcGIS Pro execution worker.
    """

    UNRESOLVED_VALUES = {
        "USER_SELECT_REQUIRED",
        "USER_INPUT_REQUIRED",
        "NOT_PROVIDED",
        "UNKNOWN",
        "TBD",
        ""
    }

    def __init__(self, checkpointer=None):

        self.planner = GISPlanningAgent()
        self.validator = WorkflowValidator()

        # Development checkpoint storage.
        self.checkpointer = (
            checkpointer if checkpointer is not None
            else MemorySaver()
        )

        self.graph = self._build_graph()

    # ==================================================
    # NODE 1: PLANNING
    # ==================================================

    def planning_node(self, state: GeoSentinelState):

        try:

            workflow = self.planner.plan(
                state["user_request"]
            )

            workflow_data = workflow.model_dump(mode="json")

            # Apply GIS inputs supplied by the user.
            resolved_inputs = state.get(
                "resolved_inputs", {}
            )

            for step in workflow_data.get("steps", []):

                step_id = step["step_id"]

                step_inputs = resolved_inputs.get(
                    step_id, {}
                )

                step["inputs"].update(step_inputs)

            return {
                "workflow": workflow_data,
                "planning_errors": [],
                "overall_status": "PLANNED",
                "messages": [
                    "GIS workflow successfully generated."
                ]
            }

        except Exception as exc:

            return {
                "workflow": {},
                "planning_errors": [str(exc)],
                "overall_status": "PLANNING_FAILED",
                "messages": [
                    f"Planning failed: {str(exc)}"
                ]
            }

    # ==================================================
    # NODE 2: INPUT RESOLUTION
    # ==================================================

    def input_resolution_node(self, state: GeoSentinelState):

        workflow = state.get("workflow", {})

        missing_inputs = []

        for step in workflow.get("steps", []):

            for input_name, input_value in step.get(
                "inputs", {}
            ).items():

                unresolved = input_value is None

                if isinstance(input_value, str):

                    unresolved = (
                        input_value.strip().upper()
                        in self.UNRESOLVED_VALUES
                    )

                if unresolved:

                    missing_inputs.append(
                        f"{step['step_id']}.{input_name}"
                    )

        if missing_inputs:

            return {
                "missing_inputs": missing_inputs,
                "input_resolution_status": "INCOMPLETE",
                "overall_status": "INPUT_REQUIRED",
                "messages": [
                    "GIS input resolution is incomplete."
                ]
            }

        return {
            "missing_inputs": [],
            "input_resolution_status": "COMPLETE",
            "overall_status": "INPUTS_RESOLVED",
            "messages": [
                "All workflow inputs have been supplied."
            ]
        }

    # ==================================================
    # NODE 3: VALIDATION
    # ==================================================

    def validation_node(self, state: GeoSentinelState):

        workflow = state.get("workflow", {})

        if not workflow:

            return {
                "validation_result": {
                    "valid": False,
                    "errors": ["No workflow available."]
                },
                "validation_errors": [
                    "No workflow available."
                ],
                "overall_status": "VALIDATION_FAILED"
            }

        result = self.validator.validate(workflow)

        return {
            "validation_result": result,
            "validation_errors": result.get("errors", []),
            "overall_status": (
                "VALIDATED"
                if result.get("valid", False)
                else "VALIDATION_FAILED"
            )
        }

    # ==================================================
    # NODE 4: HUMAN APPROVAL
    # ==================================================

    def approval_node(self, state: GeoSentinelState):

        workflow = state["workflow"]

        approval_request = {
            "event": "GEOSENTINEL_APPROVAL_REQUIRED",
            "workflow_id": workflow["workflow_id"],
            "workflow_title": workflow["title"],
            "description": workflow["description"],
            "steps": workflow["steps"],
            "message": (
                "Review the GIS workflow and explicitly "
                "approve or reject execution."
            )
        }

        # Pause graph execution until a decision is received.
        decision = interrupt(approval_request)

        approved = (
            isinstance(decision, dict)
            and decision.get("approved") is True
        )

        if approved:

            approval_id = (
                "GS-APPROVAL-"
                + uuid.uuid4().hex[:10].upper()
            )

            workflow["approval_id"] = approval_id
            workflow["status"] = "APPROVED"

            return {
                "workflow": workflow,
                "approval_status": "APPROVED",
                "approval_id": approval_id,
                "approval_decision": decision,
                "overall_status": "APPROVED",
                "messages": [
                    "Human approval successfully received."
                ]
            }

        workflow["status"] = "REJECTED"

        return {
            "workflow": workflow,
            "approval_status": "REJECTED",
            "approval_id": None,
            "approval_decision": (
                decision if isinstance(decision, dict) else {}
            ),
            "overall_status": "REJECTED",
            "messages": [
                "Workflow rejected by the user."
            ]
        }

    # ==================================================
    # NODE 5: EXECUTION HANDOFF
    # ==================================================

    def execution_handoff_node(self, state: GeoSentinelState):

        workflow = state.get("workflow", {})

        # Independent authorization checks.
        if state.get("approval_status") != "APPROVED":

            raise PermissionError(
                "Explicit human approval is required."
            )

        if not state.get("approval_id"):

            raise PermissionError(
                "Valid approval ID is required."
            )

        if not state.get("validation_result", {}).get("valid"):

            raise ValueError(
                "Workflow validation has not passed."
            )

        if state.get("input_resolution_status") != "COMPLETE":

            raise ValueError(
                "GIS inputs have not been resolved."
            )

        payload = {
            "job_id": (
                "GS-JOB-"
                + uuid.uuid4().hex[:10].upper()
            ),
            "workflow_id": workflow["workflow_id"],
            "approval_id": state["approval_id"],
            "approval_status": "APPROVED",
            "execution_status": "PENDING",
            "steps": workflow["steps"]
        }

        return {
            "execution_payload": payload,
            "execution_status": "READY_FOR_ARCGIS_PRO",
            "overall_status": "AWAITING_ARCGIS_PRO",
            "messages": [
                "Approved workflow prepared for ArcGIS Pro.",
                "Execution handoff created.",
                "No GIS operation has been executed yet."
            ]
        }

    # ==================================================
    # ROUTING
    # ==================================================

    def route_after_planning(self, state: GeoSentinelState):

        if state.get("planning_errors"):
            return "end"

        return "input_resolution"

    def route_after_input_resolution(
        self,
        state: GeoSentinelState
    ):

        if state.get("input_resolution_status") != "COMPLETE":
            return "end"

        return "validate"

    def route_after_validation(self, state: GeoSentinelState):

        result = state.get("validation_result", {})

        if not result.get("valid", False):
            return "end"

        return "approval"

    def route_after_approval(self, state: GeoSentinelState):

        if state.get("approval_status") == "APPROVED":
            return "execution_handoff"

        return "end"

    # ==================================================
    # GRAPH CONSTRUCTION
    # ==================================================

    def _build_graph(self):

        builder = StateGraph(GeoSentinelState)

        # Register nodes.
        builder.add_node(
            "planning",
            self.planning_node
        )

        builder.add_node(
            "input_resolution",
            self.input_resolution_node
        )

        builder.add_node(
            "validation",
            self.validation_node
        )

        builder.add_node(
            "approval",
            self.approval_node
        )

        builder.add_node(
            "execution_handoff",
            self.execution_handoff_node
        )

        # Entry point.
        builder.add_edge(START, "planning")

        # Planning -> Input Resolution.
        builder.add_conditional_edges(
            "planning",
            self.route_after_planning,
            {
                "input_resolution": "input_resolution",
                "end": END
            }
        )

        # Input Resolution -> Validation.
        builder.add_conditional_edges(
            "input_resolution",
            self.route_after_input_resolution,
            {
                "validate": "validation",
                "end": END
            }
        )

        # Validation -> Approval.
        builder.add_conditional_edges(
            "validation",
            self.route_after_validation,
            {
                "approval": "approval",
                "end": END
            }
        )

        # Approval -> Execution Handoff.
        builder.add_conditional_edges(
            "approval",
            self.route_after_approval,
            {
                "execution_handoff": "execution_handoff",
                "end": END
            }
        )

        # Finish after preparing handoff.
        builder.add_edge(
            "execution_handoff",
            END
        )

        return builder.compile(
            checkpointer=self.checkpointer
        )

    # ==================================================
    # PUBLIC API: START WORKFLOW
    # ==================================================

    def invoke(
        self,
        user_request: str,
        thread_id: str,
        resolved_inputs: Optional[
            dict[str, dict[str, Any]]
        ] = None
    ):

        if not user_request or not user_request.strip():

            raise ValueError(
                "User request cannot be empty."
            )

        if not thread_id or not thread_id.strip():

            raise ValueError(
                "Thread ID cannot be empty."
            )

        initial_state = {
            "user_request": user_request,
            "resolved_inputs": resolved_inputs or {},
            "messages": []
        }

        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }

        return self.graph.invoke(
            initial_state,
            config=config
        )

    # ==================================================
    # PUBLIC API: RESUME AFTER HUMAN DECISION
    # ==================================================

    def resume(
        self,
        thread_id: str,
        approved: bool
    ):

        if not thread_id or not thread_id.strip():

            raise ValueError(
                "Thread ID cannot be empty."
            )

        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }

        return self.graph.invoke(
            Command(
                resume={
                    "approved": approved
                }
            ),
            config=config
        )

    # ==================================================
    # PUBLIC API: GET WORKFLOW STATE
    # ==================================================

    def get_workflow_state(self, thread_id: str):

        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }

        snapshot = self.graph.get_state(config)

        return {
            "values": snapshot.values,
            "next": snapshot.next,
            "tasks": [
                {
                    "name": task.name,
                    "interrupts": [
                        item.value for item in task.interrupts
                    ]
                }
                for task in snapshot.tasks
            ]
        }