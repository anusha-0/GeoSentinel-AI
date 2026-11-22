from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class CreateWorkflowRequest(BaseModel):
    user_request: str = Field(min_length=1, max_length=4000)
    thread_id: str = Field(min_length=1, max_length=128)


class ResolveInputsRequest(BaseModel):
    resolved_inputs: dict[str, dict] = Field(min_length=1)


class ApprovalRequest(BaseModel):
    approved: bool


def _service(request: Request):
    return request.app.state.workflow_service


@router.post("")
def create_workflow(body: CreateWorkflowRequest, request: Request):
    try:
        return _service(request).create(body.user_request, body.thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{thread_id}")
def get_workflow(thread_id: str, request: Request):
    try:
        return _service(request).get(thread_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{thread_id}/resolve")
def resolve_workflow_inputs(thread_id: str, body: ResolveInputsRequest, request: Request):
    try:
        return _service(request).resolve(thread_id, body.resolved_inputs)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{thread_id}/approve")
def approve_workflow(thread_id: str, body: ApprovalRequest, request: Request):
    try:
        return _service(request).approve(thread_id, body.approved)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{thread_id}/results")
def get_workflow_results(thread_id: str, request: Request):
    state = _service(request).get(thread_id)
    return {"thread_id": thread_id, "workflow": state.get("values", {}),
            "execution": request.app.state.verification_service.get_status()}


@router.post("/{thread_id}/synchronize")
def synchronize_workflow(thread_id: str, request: Request):
    try:
        return _service(request).synchronize(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
