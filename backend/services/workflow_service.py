from orchestration.workflow_graph import GeoSentinelWorkflowEngine
from backend.services.execution_bridge import ExecutionBridge
from backend.services.workflow_lifecycle_service import WorkflowLifecycleService


class WorkflowService:
    def __init__(self, engine: GeoSentinelWorkflowEngine, bridge=None):
        self.engine = engine
        self.bridge = bridge or ExecutionBridge()
        self.lifecycle = WorkflowLifecycleService(engine, self.bridge)

    def create(self, request: str, thread_id: str):
        return self.engine.invoke(request, thread_id)

    def resolve(self, thread_id: str, resolved_inputs: dict):
        return self.engine.resolve_inputs(thread_id, resolved_inputs)

    def approve(self, thread_id: str, approved: bool):
        state = self.engine.resume(thread_id, approved)
        payload = state.get("execution_payload")
        if approved and payload:
            job = self.bridge.publish(payload)
            state = dict(state)
            state["bridge_job"] = job
        return state

    def synchronize(self, thread_id: str):
        return self.lifecycle.synchronize(thread_id)

    def get(self, thread_id: str):
        return self.engine.get_workflow_state(thread_id)
