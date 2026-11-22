import json

import pytest

from pathlib import Path

from backend.services.execution_bridge import ExecutionBridge


def valid_payload(
    job_id="J1",
    workflow_id="W1",
    approval_id="A1",
):

    return {
        "job_id": job_id,
        "workflow_id": workflow_id,
        "approval_id": approval_id,
        "approval_status": "APPROVED",
        "steps": [
            {
                "step_id": "STEP-001",
                "operation_id": "buffer",
                "inputs": {
                    "input_features": "Test_Settlements",
                },
                "parameters": {
                    "distance": "500 Meters",
                    "dissolve_option": "ALL",
                },
                "output_name": "Test_Buffer",
            }
        ],
    }


def write_json(path, data):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(data, indent=4),
        encoding="utf-8",
    )


def test_publish_creates_approved_job(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    result = bridge.publish(valid_payload())

    assert result["job_id"] == "J1"
    assert result["workflow_id"] == "W1"
    assert result["approval_id"] == "A1"

    assert result["execution_status"] == "PENDING"

    stored = bridge.get_job()

    assert stored == result


def test_unapproved_payload_is_rejected(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    payload = valid_payload()
    payload["approval_status"] = "REJECTED"

    with pytest.raises(PermissionError):
        bridge.publish(payload)


def test_missing_identity_is_rejected(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    payload = valid_payload()
    del payload["approval_id"]

    with pytest.raises(ValueError, match="approval_id"):
        bridge.publish(payload)


def test_unsupported_operation_is_rejected(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    payload = valid_payload()
    payload["steps"][0]["operation_id"] = "clip"

    with pytest.raises(ValueError, match="buffer"):
        bridge.publish(payload)


def test_pending_job_blocks_new_publish(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    bridge.publish(valid_payload())

    with pytest.raises(FileExistsError):
        bridge.publish(
            valid_payload(
                job_id="J2",
                workflow_id="W2",
                approval_id="A2",
            )
        )


def test_previous_successful_job_is_archived(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    old_job = bridge.publish(valid_payload())

    execution = {
        "job_id": "J1",
        "workflow_id": "W1",
        "approval_id": "A1",
        "status": "SUCCESS",
    }

    report = {
        "job_id": "J1",
        "workflow_id": "W1",
        "approval_id": "A1",
        "verification_status": "VERIFIED",
    }

    write_json(
        bridge.result_file,
        execution,
    )

    write_json(
        bridge.report_file,
        report,
    )

    # Simulate the earlier worker version which left
    # approved_job.json marked as PENDING.

    new_job = bridge.publish(
        valid_payload(
            job_id="J2",
            workflow_id="W2",
            approval_id="A2",
        )
    )

    assert new_job["job_id"] == "J2"

    assert bridge.get_execution() is None
    assert bridge.get_verification() is None

    assert bridge.get_job()["job_id"] == "J2"

    archived = list(
        bridge.archive_dir.iterdir()
    )

    assert len(archived) == 1

    archived_files = {
        path.name
        for path in archived[0].iterdir()
    }

    assert "approved_job.json" in archived_files
    assert "execution_result.json" in archived_files
    assert "verification_report.json" in archived_files


def test_success_without_verification_blocks_new_job(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    bridge.publish(valid_payload())

    write_json(
        bridge.result_file,
        {
            "job_id": "J1",
            "workflow_id": "W1",
            "approval_id": "A1",
            "status": "SUCCESS",
        },
    )

    with pytest.raises(FileExistsError):
        bridge.publish(
            valid_payload(
                job_id="J2",
                workflow_id="W2",
                approval_id="A2",
            )
        )


def test_mismatched_execution_identity_blocks_new_job(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    bridge.publish(valid_payload())

    write_json(
        bridge.result_file,
        {
            "job_id": "OTHER",
            "workflow_id": "W1",
            "approval_id": "A1",
            "status": "SUCCESS",
        },
    )

    with pytest.raises(FileExistsError):
        bridge.publish(
            valid_payload(
                job_id="J2",
                workflow_id="W2",
                approval_id="A2",
            )
        )


def test_atomic_write_leaves_valid_json(tmp_path):

    bridge = ExecutionBridge(tmp_path)

    bridge.publish(valid_payload())

    stored = json.loads(
        bridge.job_file.read_text(
            encoding="utf-8"
        )
    )

    assert stored["job_id"] == "J1"

    temporary_files = list(
        tmp_path.glob("*.tmp")
    )

    assert temporary_files == []