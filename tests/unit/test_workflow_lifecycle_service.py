import pytest

from types import SimpleNamespace

from backend.services.workflow_lifecycle_service import (
    WorkflowLifecycleService,
)


class FakeGraph:

    def __init__(self, values):
        self.values = values
        self.updates = []

    def get_state(self, config):
        return SimpleNamespace(values=self.values)

    def update_state(self, config, update):
        self.updates.append(update)
        self.values.update(update)


class FakeBridge:

    def __init__(self, job=None, execution=None, report=None):
        self.job_file = "job"
        self.job = job
        self.execution = execution
        self.report = report

    def _read(self, path):
        return self.job

    def get_execution(self):
        return self.execution

    def get_verification(self):
        return self.report


def artifacts(status="SUCCESS", verification="VERIFIED"):

    ids = {
        "job_id": "J1",
        "workflow_id": "W1",
        "approval_id": "A1",
    }

    job = dict(ids)

    execution = dict(
        ids,
        status=status,
    )

    report = dict(
        ids,
        execution_status="SUCCESS",
        verification_status=verification,
        summary={
            "total_checks": 11,
            "passed": 11,
            "failed": 0,
            "warnings": 0,
            "not_run": 0,
        },
    )

    return job, execution, report


def service(status="SUCCESS", verification="VERIFIED"):

    job, execution, report = artifacts(
        status,
        verification,
    )

    values = {
        "execution_payload": {
            "job_id": "J1",
            "workflow_id": "W1",
            "approval_id": "A1",
        },
        "workflow": {
            "workflow_id": "W1",
            "steps": [
                {
                    "step_id": "S1",
                    "status": "PENDING",
                }
            ],
        },
    }

    graph = FakeGraph(values)

    engine = SimpleNamespace(
        _config=lambda tid: {
            "configurable": {
                "thread_id": tid
            }
        },
        graph=graph,
    )

    bridge = FakeBridge(
        job,
        execution,
        report,
    )

    return WorkflowLifecycleService(engine, bridge), graph


# ---------------------------------------------------------
# SUCCESS AND FAILURE TESTS
# ---------------------------------------------------------

def test_success_and_verified_completes_workflow_and_step():

    svc, graph = service()

    result = svc.synchronize("T1")

    assert result["synchronization_status"] == "COMPLETED"

    assert (
        graph.updates[0]["workflow"]["steps"][0]["status"]
        == "SUCCESS"
    )

    assert graph.updates[0]["verification_status"] == "VERIFIED"


def test_execution_failure_fails_workflow():

    svc, graph = service(status="FAILED")

    result = svc.synchronize("T1")

    assert result["synchronization_status"] == "FAILED"

    assert (
        graph.updates[0]["workflow"]["steps"][0]["status"]
        == "FAILED"
    )


def test_verification_failure_fails_workflow():

    svc, graph = service(verification="FAILED")

    result = svc.synchronize("T1")

    assert result["synchronization_status"] == "FAILED"


def test_warning_does_not_complete_workflow():

    svc, graph = service(verification="WARNING")

    result = svc.synchronize("T1")

    assert result["synchronization_status"] == "AWAITING_VERIFICATION"

    assert not graph.updates


# ---------------------------------------------------------
# IDENTITY VALIDATION TESTS
# ---------------------------------------------------------

def test_mismatched_job_identity_rejected():

    svc, _ = service()

    svc.bridge.execution["job_id"] = "OTHER"

    with pytest.raises(ValueError, match="job_id"):
        svc.synchronize("T1")


def test_missing_workflow_identity_is_rejected():

    svc, _ = service()

    del svc.bridge.execution["approval_id"]

    with pytest.raises(ValueError, match="approval_id"):
        svc.synchronize("T1")


def test_missing_checkpoint_identity_is_rejected():

    svc, _ = service()

    svc.engine.graph.values[
        "execution_payload"
    ]["workflow_id"] = ""

    with pytest.raises(ValueError, match="workflow_id"):
        svc.synchronize("T1")


# ---------------------------------------------------------
# MISSING ARTIFACT TESTS
# ---------------------------------------------------------

def test_missing_execution_waits_without_mutation():

    svc, graph = service()

    svc.bridge.execution = None

    result = svc.synchronize("T1")

    assert result["synchronization_status"] == "AWAITING_EXECUTION"

    assert not graph.updates


def test_missing_report_waits_without_mutation():

    svc, graph = service()

    svc.bridge.report = None

    result = svc.synchronize("T1")

    assert result["synchronization_status"] == "AWAITING_VERIFICATION"

    assert not graph.updates


# ---------------------------------------------------------
# IDEMPOTENCY TEST
# ---------------------------------------------------------

def test_repeated_sync_is_idempotent():

    svc, graph = service()

    svc.synchronize("T1")
    svc.synchronize("T1")

    assert len(graph.updates) == 2

    assert graph.updates[0] == graph.updates[1]


# ---------------------------------------------------------
# VERIFICATION SUMMARY TESTS
# ---------------------------------------------------------

def test_missing_verification_summary_is_rejected():

    svc, _ = service()

    svc.bridge.report["summary"] = None

    with pytest.raises(ValueError, match="summary"):
        svc.synchronize("T1")


def test_missing_summary_counter_is_rejected():

    svc, _ = service()

    del svc.bridge.report["summary"]["warnings"]

    with pytest.raises(ValueError, match="warnings"):
        svc.synchronize("T1")


def test_negative_summary_counter_is_rejected():

    svc, _ = service()

    svc.bridge.report["summary"]["passed"] = -1

    with pytest.raises(ValueError, match="passed"):
        svc.synchronize("T1")


def test_inconsistent_summary_total_is_rejected():

    svc, _ = service()

    svc.bridge.report["summary"]["total_checks"] = 12

    with pytest.raises(ValueError, match="total_checks"):
        svc.synchronize("T1")


# ---------------------------------------------------------
# MULTI-STEP SAFETY TEST
# ---------------------------------------------------------

def test_multiple_steps_are_not_silently_marked_successful():

    svc, _ = service()

    svc.engine.graph.values["workflow"]["steps"].append(
        {
            "step_id": "S2",
            "status": "PENDING",
        }
    )

    with pytest.raises(ValueError, match="exactly one"):
        svc.synchronize("T1")