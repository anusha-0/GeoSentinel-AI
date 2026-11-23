export type WorkflowStep = {
  step_id: string;
  operation_id: string;
  description: string;
  inputs: Record<string, unknown>;
  parameters: Record<string, unknown>;
  output_name?: string | null;
  status: string;
};

export type GISWorkflow = {
  workflow_id: string;
  request: string;
  title: string;
  description: string;
  status: string;
  steps: WorkflowStep[];
  approval_required: boolean;
  approval_id?: string | null;
};

export type VerificationSummary = {
  total_checks: number;
  passed: number;
  warnings: number;
  failed: number;
  not_run: number;
};

export type VerificationReport = {
  verification_version?: string;
  verification_status?: string;
  job_id?: string;
  workflow_id?: string;
  approval_id?: string;
  summary?: VerificationSummary;
  checks?: unknown[] | Record<string, unknown>;
};

export type WorkflowValues = {
  user_request?: string;
  workflow?: GISWorkflow;
  missing_inputs?: string[];
  input_resolution_status?: string;
  validation_result?: { valid?: boolean; errors?: string[]; warnings?: string[] };
  approval_status?: string;
  approval_id?: string | null;
  execution_payload?: {
    job_id?: string;
    workflow_id?: string;
    approval_id?: string;
    execution_status?: string;
  };
  execution_status?: string;
  execution_result?: Record<string, unknown>;
  verification_report?: VerificationReport;
  verification_status?: string;
  overall_status?: string;
  messages?: string[];
};

export type WorkflowInterrupt = {
  event?: string;
  workflow_id?: string;
  missing_inputs?: string[];
  message?: string;
};

export type WorkflowTask = {
  name: string;
  interrupts?: WorkflowInterrupt[];
};

export type WorkflowCheckpoint = {
  values: WorkflowValues;
  next?: string[];
  tasks?: WorkflowTask[];
};

export type ApiHealth = {
  application: string;
  version: string;
  status: "healthy" | "unhealthy" | string;
  execution_model?: string;
};
