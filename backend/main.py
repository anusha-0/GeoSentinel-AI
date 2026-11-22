from contextlib import asynccontextmanager
from pathlib import Path
import os

from fastapi import FastAPI
from langgraph.checkpoint.sqlite import SqliteSaver

from backend.api.workflows import router as workflows_router
from backend.services.workflow_service import WorkflowService
from backend.services.verification_service import VerificationService
from orchestration.workflow_graph import GeoSentinelWorkflowEngine

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = Path(os.getenv("GEOSENTINEL_CHECKPOINT_DB", PROJECT_ROOT / "runtime" / "geosentinel_checkpoints.sqlite"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the SQLite connection open for the application's full lifetime.
    with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        engine = GeoSentinelWorkflowEngine(checkpointer=checkpointer)
        app.state.workflow_engine = engine
        app.state.workflow_service = WorkflowService(engine)
        app.state.verification_service = VerificationService()
        yield


app = FastAPI(title="GeoSentinel AI API", version="0.8.3", lifespan=lifespan)
app.include_router(workflows_router)


@app.get("/api/health", tags=["system"])
def health():
    return {"application": "GeoSentinel AI", "version": "0.8.3", "status": "healthy",
            "execution_model": "ArcGIS Pro worker; API does not execute ArcPy"}
