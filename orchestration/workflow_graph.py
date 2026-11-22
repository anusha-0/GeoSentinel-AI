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
    LangGraph workflow engine.

    Planning -> input resolution -> validation -> human approval
    -> execution handoff. ArcPy remains isolated in the ArcGIS Pro worker.
    """

    UNRESOLVED_VALUES = {
        "USER_SELECT_REQUIRED",
        "USER_INPUT_REQUIRED",
        "NOT_PROVIDED",
        "UNKNOWN",
        "TBD",
        "",
    }

    def __init__(self, checkpointer=None):
        self.planner = GISPlanningAgent()
        self.validator = WorkflowValidator()
        self.checkpointer = checkpointer if checkpointer is not None else MemorySaver()
        self.graph = self._build_graph()

    @staticmethod
    def _config(thread_id: str) -> dict:
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("Thread ID cannot be empty.")
        return {"configurable": {"thread_id": thread_id}}

    @classmethod
    def _is_unresolved(cls, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip().upper() in cls.UNRESOLVED_VALUES
        return False

    # NODE 1: deterministic planning
    def planning_node(self, state: GeoSentinelState):
        try:
            workflow = self.planner.plan(state["user_request"])
            workflow_data = workflow.model_dump(mode="json")
            supplied = state.get("resolved_inputs", {}) or {}

            for step in workflow_data.get("steps", []):
                step_inputs = supplied.get(step["step_id"], {})
                if isinstance(step_inputs, dict):
                    step["inputs"].update(step_inputs)

            return {
                "workflow": workflow_data,
                "planning_errors": [],
                "overall_status": "PLANNED",
                "messages": ["GIS workflow successfully generated."],
            }
        except Exception as exc:
            return {
                "workflow": {},
                "planning_errors": [str(exc)],
                "overall_status": "PLANNING_FAILED",
                "messages": [f"Planning failed: {exc}"],
            }

    # NODE 2: determine whether user-supplied GIS inputs are missing
    def input_resolution_node(self, state: GeoSentinelState):
        workflow = state.get("workflow", {})
        missing = []

        for step in workflow.get("steps", []):
            for name, value in step.get("inputs", {}).items():
                if self._is_unresolved(value):
                    missing.append(f"{step['step_id']}.{name}")

        complete = not missing
        return {
            "missing_inputs": missing,
            "input_resolution_status": "COMPLETE" if complete else "INCOMPLETE",
            "overall_status": "INPUTS_RESOLVED" if complete else "INPUT_REQUIRED",
            "messages": (
                ["All workflow inputs have been supplied."]
                if complete else ["GIS input resolution is incomplete."]
            ),
        }

    # NODE 2A: interrupt and wait for GIS layer selections
    def await_inputs_node(self, state: GeoSentinelState):
        workflow = state.get("workflow", {})
        request = {
            "event": "GEOSENTINEL_INPUT_REQUIRED",
            "workflow_id": workflow.get("workflow_id"),
            "missing_inputs": state.get("missing_inputs", []),
            "steps": workflow.get("steps", []),
            "message": "Select values for the unresolved GIS workflow inputs.",
        }
        decision = interrupt(request)

        if not isinstance(decision, dict):
            raise ValueError("Input resolution must be an object.")

        supplied = decision.get("resolved_inputs")
        if not isinstance(supplied, dict) or not supplied:
            raise ValueError("resolved_inputs must contain at least one step mapping.")

        steps = workflow.get("steps", [])
        steps_by_id = {step["step_id"]: step for step in steps}
        known_step_ids = set(steps_by_id)

        unknown_steps = set(supplied) - known_step_ids
        if unknown_steps:
            raise ValueError(f"Unknown workflow step IDs: {sorted(unknown_steps)}")

        merged_resolved = dict(state.get("resolved_inputs", {}) or {})

        for step_id, values in supplied.items():
            if not isinstance(values, dict) or not values:
                raise ValueError(f"Inputs for {step_id} must be a non-empty object.")

            step = steps_by_id[step_id]
            known_input_names = set(step.get("inputs", {}))
            unknown_inputs = set(values) - known_input_names
            if unknown_inputs:
                raise ValueError(
                    f"Unknown inputs for {step_id}: {sorted(unknown_inputs)}"
                )

            for input_name, input_value in values.items():
                if self._is_unresolved(input_value):
                    raise ValueError(
                        f"{step_id}.{input_name} must be resolved to a real value."
                    )
                if not isinstance(input_value, str):
                    raise ValueError(
                        f"{step_id}.{input_name} must be a string layer/dataset name."
                    )
                step["inputs"][input_name] = input_value

            merged_step_values = dict(merged_resolved.get(step_id, {}))
            merged_step_values.update(values)
            merged_resolved[step_id] = merged_step_values

        return {
            "workflow": workflow,
            "resolved_inputs": merged_resolved,
            "messages": ["User-supplied GIS inputs received; rechecking completeness."],
        }

    # NODE 3: registry-backed workflow validation
    def validation_node(self, state: GeoSentinelState):
        workflow = state.get("workflow", {})
        if not workflow:
            result = {"valid": False, "errors": ["No workflow available."]}
        else:
            result = self.validator.validate(workflow)

        return {
            "validation_result": result,
            "validation_errors": result.get("errors", []),
            "overall_status": "VALIDATED" if result.get("valid") else "VALIDATION_FAILED",
        }

    # NODE 4: explicit human approval
    def approval_node(self, state: GeoSentinelState):
        workflow = state["workflow"]
        decision = interrupt({
            "event": "GEOSENTINEL_APPROVAL_REQUIRED",
            "workflow_id": workflow["workflow_id"],
            "workflow_title": workflow["title"],
            "description": workflow["description"],
            "steps": workflow["steps"],
            "message": "Review the GIS workflow and explicitly approve or reject execution.",
        })

        approved = isinstance(decision, dict) and decision.get("approved") is True
        if approved:
            approval_id = "GS-APPROVAL-" + uuid.uuid4().hex[:10].upper()
            workflow["approval_id"] = approval_id
            workflow["status"] = "APPROVED"
            return {
                "workflow": workflow,
                "approval_status": "APPROVED",
                "approval_id": approval_id,
                "approval_decision": decision,
                "overall_status": "APPROVED",
                "messages": ["Human approval successfully received."],
            }

        workflow["status"] = "REJECTED"
        return {
            "workflow": workflow,
            "approval_status": "REJECTED",
            "approval_id": None,
            "approval_decision": decision if isinstance(decision, dict) else {},
            "overall_status": "REJECTED",
            "messages": ["Workflow rejected by the user."],
        }

    # NODE 5: create handoff payload only; ArcGIS Pro executes separately
    def execution_handoff_node(self, state: GeoSentinelState):
        workflow = state.get("workflow", {})

        if state.get("approval_status") != "APPROVED" or not state.get("approval_id"):
            raise PermissionError("Explicit human approval and approval ID are required.")
        if not state.get("validation_result", {}).get("valid"):
            raise ValueError("Workflow validation has not passed.")
        if state.get("input_resolution_status") != "COMPLETE":
            raise ValueError("GIS inputs have not been resolved.")

        payload = {
            "job_id": "GS-JOB-" + uuid.uuid4().hex[:10].upper(),
            "workflow_id": workflow["workflow_id"],
            "approval_id": state["approval_id"],
            "approval_status": "APPROVED",
            "execution_status": "PENDING",
            "steps": workflow["steps"],
        }
        return {
            "execution_payload": payload,
            "execution_status": "READY_FOR_ARCGIS_PRO",
            "overall_status": "AWAITING_ARCGIS_PRO",
            "messages": [
                "Approved workflow prepared for ArcGIS Pro.",
                "Execution handoff created.",
                "No GIS operation has been executed yet.",
            ],
        }

    # ROUTING
    @staticmethod
    def route_after_planning(state):
        return "end" if state.get("planning_errors") else "input_resolution"

    @staticmethod
    def route_after_input_resolution(state):
        return "await_inputs" if state.get("input_resolution_status") != "COMPLETE" else "validate"

    @staticmethod
    def route_after_validation(state):
        return "approval" if state.get("validation_result", {}).get("valid") else "end"

    @staticmethod
    def route_after_approval(state):
        return "execution_handoff" if state.get("approval_status") == "APPROVED" else "end"

    def _build_graph(self):
        builder = StateGraph(GeoSentinelState)
        builder.add_node("planning", self.planning_node)
        builder.add_node("input_resolution", self.input_resolution_node)
        builder.add_node("await_inputs", self.await_inputs_node)
        builder.add_node("validation", self.validation_node)
        builder.add_node("approval", self.approval_node)
        builder.add_node("execution_handoff", self.execution_handoff_node)

        builder.add_edge(START, "planning")
        builder.add_conditional_edges(
            "planning", self.route_after_planning,
            {"input_resolution": "input_resolution", "end": END},
        )
        builder.add_conditional_edges(
            "input_resolution", self.route_after_input_resolution,
            {"await_inputs": "await_inputs", "validate": "validation"},
        )
        builder.add_edge("await_inputs", "input_resolution")
        builder.add_conditional_edges(
            "validation", self.route_after_validation,
            {"approval": "approval", "end": END},
        )
        builder.add_conditional_edges(
            "approval", self.route_after_approval,
            {"execution_handoff": "execution_handoff", "end": END},
        )
        builder.add_edge("execution_handoff", END)
        return builder.compile(checkpointer=self.checkpointer)

    # PUBLIC API: start workflow
    def invoke(
        self,
        user_request: str,
        thread_id: str,
        resolved_inputs: Optional[dict[str, dict[str, Any]]] = None,
    ):
        if not isinstance(user_request, str) or not user_request.strip():
            raise ValueError("User request cannot be empty.")
        config = self._config(thread_id)
        initial_state = {
            "user_request": user_request,
            "resolved_inputs": resolved_inputs or {},
            "messages": [],
        }
        return self.graph.invoke(initial_state, config=config)

    # PUBLIC API: resolve previously missing GIS inputs and resume graph
    def resolve_inputs(self, thread_id: str, resolved_inputs: dict):
        config = self._config(thread_id)
        if not isinstance(resolved_inputs, dict) or not resolved_inputs:
            raise ValueError("resolved_inputs must be a non-empty object.")

        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            raise ValueError(f"No workflow found for thread_id '{thread_id}'.")
        if not snapshot.interrupts:
            raise ValueError("Workflow is not currently waiting for GIS input resolution.")

        pending = snapshot.interrupts[0].value
        if pending.get("event") != "GEOSENTINEL_INPUT_REQUIRED":
            raise ValueError("Workflow is not paused at the GIS input-resolution step.")

        return self.graph.invoke(
            Command(resume={"resolved_inputs": resolved_inputs}),
            config=config,
        )

    # PUBLIC API: resume human approval
    def resume(self, thread_id: str, approved: bool):
        config = self._config(thread_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            raise ValueError(f"No workflow found for thread_id '{thread_id}'.")
        if not snapshot.interrupts:
            raise ValueError("Workflow is not currently waiting for human approval.")

        pending = snapshot.interrupts[0].value
        if pending.get("event") != "GEOSENTINEL_APPROVAL_REQUIRED":
            raise ValueError("Workflow is not paused at the human-approval step.")

        return self.graph.invoke(
            Command(resume={"approved": bool(approved)}),
            config=config,
        )

    # PUBLIC API: read checkpoint state
    def get_workflow_state(self, thread_id: str):
        config = self._config(thread_id)
        snapshot = self.graph.get_state(config)
        if not snapshot.values:
            raise ValueError(f"No workflow found for thread_id '{thread_id}'.")
        return {
            "values": snapshot.values,
            "next": snapshot.next,
            "tasks": [
                {
                    "name": task.name,
                    "interrupts": [item.value for item in task.interrupts],
                }
                for task in snapshot.tasks
            ],
        }
