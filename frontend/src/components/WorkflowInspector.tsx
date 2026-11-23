import { useMemo, useState } from "react";
import {
  approveWorkflow,
  getWorkflow,
  resolveWorkflowInputs,
  synchronizeWorkflow,
} from "../services/api";
import type { WorkflowCheckpoint } from "../types/workflow";

interface Props {
  threadId: string | null;
  snapshot: WorkflowCheckpoint | null;
  onSnapshotChange: (snapshot: WorkflowCheckpoint) => void;
}

function getInterrupts(snapshot: WorkflowCheckpoint | null) {
  return (snapshot?.tasks ?? []).flatMap((task) => task.interrupts ?? []);
}

function statusClass(status?: string) {
  switch (status?.toUpperCase()) {
    case "COMPLETED":
    case "SUCCESS":
    case "VERIFIED":
      return "state-success";
    case "FAILED":
    case "REJECTED":
      return "state-danger";
    case "AWAITING_ARCGIS_PRO":
    case "AWAITING_APPROVAL":
    case "VALIDATED":
      return "state-warning";
    default:
      return "state-neutral";
  }
}

export function WorkflowInspector({ threadId, snapshot, onSnapshotChange }: Props) {
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const values = snapshot?.values;
  const workflow = values?.workflow;
  const missingInputs = values?.missing_inputs ?? [];
  const interrupts = getInterrupts(snapshot);
  const waitingForApproval = interrupts.some(
    (item) => item.event === "GEOSENTINEL_APPROVAL_REQUIRED",
  );
  const canApprove = Boolean(values?.validation_result?.valid && waitingForApproval);
  const hasExecutionPayload = Boolean(values?.execution_payload?.job_id);
  const verificationSummary = values?.verification_report?.summary;

  const inputDescriptors = useMemo(
    () => missingInputs.map((path) => {
      const separator = path.indexOf(".");
      return {
        path,
        stepId: separator >= 0 ? path.slice(0, separator) : "STEP-001",
        inputName: separator >= 0 ? path.slice(separator + 1) : path,
      };
    }),
    [missingInputs],
  );

  async function refresh() {
    if (!threadId) return;
    const latest = await getWorkflow(threadId);
    onSnapshotChange(latest);
  }

  async function runAction(action: string, work: () => Promise<unknown>) {
    setBusyAction(action);
    setActionError(null);
    try {
      await work();
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The workflow action failed.");
    } finally {
      setBusyAction(null);
    }
  }

  function handleResolve() {
    if (!threadId) return;
    const resolved: Record<string, Record<string, string>> = {};
    for (const descriptor of inputDescriptors) {
      const value = inputValues[descriptor.path]?.trim();
      if (!value) {
        setActionError(`Enter a dataset name for ${descriptor.path}.`);
        return;
      }
      resolved[descriptor.stepId] ??= {};
      resolved[descriptor.stepId][descriptor.inputName] = value;
    }
    void runAction("resolve", () => resolveWorkflowInputs(threadId, resolved));
  }

  function handleApproval(approved: boolean) {
    if (!threadId) return;
    void runAction(approved ? "approve" : "reject", () => approveWorkflow(threadId, approved));
  }

  function handleSynchronize() {
    if (!threadId) return;
    void runAction("synchronize", () => synchronizeWorkflow(threadId));
  }

  return (
    <section className="workflow-card" id="workflow-inspector" aria-label="Workflow inspector">
      <div className="card-heading">
        <div>
          <p className="eyebrow">CONTROLLED EXECUTION</p>
          <h2>Workflow</h2>
        </div>
        {values?.overall_status && (
          <span className={`state-pill ${statusClass(values.overall_status)}`}>
            {values.overall_status.replaceAll("_", " ")}
          </span>
        )}
      </div>

      {!snapshot || !workflow ? (
        <div className="empty-workflow">
          <calcite-icon icon="workflow" scale="l" />
          <strong>No active workflow</strong>
          <p>Submit a spatial request to create a plan, resolve its inputs and review the approval gate.</p>
        </div>
      ) : (
        <>
          <div className="workflow-meta">
            <div>
              <span className="meta-label">Workflow</span>
              <strong>{workflow.title}</strong>
            </div>
            <div>
              <span className="meta-label">Workflow ID</span>
              <code>{workflow.workflow_id}</code>
            </div>
            <div>
              <span className="meta-label">Thread ID</span>
              <code>{threadId}</code>
            </div>
          </div>

          <div className="step-list">
            {workflow.steps.map((step, index) => (
              <div className="workflow-step" key={step.step_id}>
                <div className="step-index">{index + 1}</div>
                <div className="step-body">
                  <strong>{step.operation_id.replaceAll("_", " ")}</strong>
                  <p>{step.description}</p>
                  <div className="step-details">
                    {Object.entries(step.parameters ?? {}).map(([key, value]) => (
                      <span key={key}>{key.replaceAll("_", " ")}: {String(value)}</span>
                    ))}
                    {step.output_name && <span>output: {step.output_name}</span>}
                  </div>
                </div>
                <span className={`step-status ${statusClass(step.status)}`}>{step.status}</span>
              </div>
            ))}
          </div>

          {missingInputs.length > 0 && (
            <div className="workflow-action-block">
              <h3>Resolve GIS inputs</h3>
              <p className="muted-text">Select the exact dataset names from your ArcGIS Pro project. GeoSentinel will not guess a layer.</p>
              {inputDescriptors.map((descriptor) => (
                <label className="field-label" key={descriptor.path}>
                  <span>{descriptor.inputName.replaceAll("_", " ")}</span>
                  <input
                    value={inputValues[descriptor.path] ?? ""}
                    onChange={(event) => setInputValues((current) => ({ ...current, [descriptor.path]: event.target.value }))}
                    placeholder="e.g. GS_Test_Settlements"
                  />
                </label>
              ))}
              <calcite-button width="full" onClick={handleResolve} disabled={busyAction !== null}>
                {busyAction === "resolve" ? "Resolving…" : "Resolve inputs"}
              </calcite-button>
            </div>
          )}

          {canApprove && (
            <div className="workflow-action-block approval-block">
              <h3>Human approval required</h3>
              <p className="muted-text">Validation passed. Review the operation and parameters above before approving the ArcGIS Pro handoff.</p>
              <div className="button-row">
                <calcite-button appearance="solid" kind="brand" onClick={() => handleApproval(true)} disabled={busyAction !== null}>
                  {busyAction === "approve" ? "Approving…" : "Approve workflow"}
                </calcite-button>
                <calcite-button appearance="outline" kind="danger" onClick={() => handleApproval(false)} disabled={busyAction !== null}>
                  Reject
                </calcite-button>
              </div>
            </div>
          )}

          {hasExecutionPayload && (
            <div className="workflow-action-block handoff-block">
              <h3>ArcGIS Pro handoff prepared</h3>
              <p className="muted-text">The approved job is ready for the ArcGIS Pro worker. The API has not executed ArcPy.</p>
              <div className="job-id"><span>Job ID</span><code>{values.execution_payload?.job_id}</code></div>
              <calcite-button appearance="outline" width="full" onClick={handleSynchronize} disabled={busyAction !== null}>
                {busyAction === "synchronize" ? "Checking artifacts…" : "Synchronize execution & verification"}
              </calcite-button>
              <p className="tiny-note">Run the approved worker and verifier in ArcGIS Pro before synchronizing.</p>
            </div>
          )}

          {verificationSummary && (
            <div className="verification-summary">
              <div className="summary-heading">
                <strong>Verification</strong>
                <span className={`state-pill ${statusClass(values.verification_status)}`}>
                  {values.verification_status ?? "UNKNOWN"}
                </span>
              </div>
              <div className="summary-grid">
                <div><strong>{verificationSummary.passed}/{verificationSummary.total_checks}</strong><span>Passed</span></div>
                <div><strong>{verificationSummary.failed}</strong><span>Failed</span></div>
                <div><strong>{verificationSummary.warnings}</strong><span>Warnings</span></div>
                <div><strong>{verificationSummary.not_run}</strong><span>Not run</span></div>
              </div>
            </div>
          )}
        </>
      )}

      {actionError && <p className="inline-error" role="alert">{actionError}</p>}
    </section>
  );
}
