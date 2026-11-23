import type {
  ApiHealth,
  WorkflowCheckpoint,
} from "../types/workflow";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String(payload.detail)
        : `Request failed (${response.status} ${response.statusText})`;
    throw new Error(detail);
  }

  return payload as T;
}

export function getHealth(): Promise<ApiHealth> {
  return request<ApiHealth>("/health");
}

export function createWorkflow(userRequest: string, threadId: string): Promise<unknown> {
  return request("/workflows", {
    method: "POST",
    body: JSON.stringify({ user_request: userRequest, thread_id: threadId }),
  });
}

export function getWorkflow(threadId: string): Promise<WorkflowCheckpoint> {
  return request<WorkflowCheckpoint>(`/workflows/${encodeURIComponent(threadId)}`);
}

export function resolveWorkflowInputs(
  threadId: string,
  resolvedInputs: Record<string, Record<string, string>>,
): Promise<unknown> {
  return request(`/workflows/${encodeURIComponent(threadId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolved_inputs: resolvedInputs }),
  });
}

export function approveWorkflow(threadId: string, approved: boolean): Promise<unknown> {
  return request(`/workflows/${encodeURIComponent(threadId)}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved }),
  });
}

export function synchronizeWorkflow(threadId: string): Promise<unknown> {
  return request(`/workflows/${encodeURIComponent(threadId)}/synchronize`, {
    method: "POST",
  });
}
