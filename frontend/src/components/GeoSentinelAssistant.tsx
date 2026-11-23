import { useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { createWorkflow, getWorkflow } from "../services/api";
import type { WorkflowCheckpoint } from "../types/workflow";

interface Props {
  onWorkflowStarted: (threadId: string, snapshot: WorkflowCheckpoint) => void;
}

type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

const SUGGESTED_PROMPTS = [
  "Create a 500-meter buffer around settlements and dissolve overlapping buffers.",
  "Identify settlements intersecting a landslide susceptibility zone.",
  "Calculate slope from an elevation raster.",
];

function createThreadId(): string {
  const suffix = crypto.randomUUID().replaceAll("-", "").slice(0, 12).toUpperCase();
  return `GS-UI-${suffix}`;
}

function responseFor(snapshot: WorkflowCheckpoint, threadId: string): string {
  const values = snapshot.values ?? {};
  const workflow = values.workflow;
  const missingInputs = values.missing_inputs ?? [];

  if (missingInputs.length > 0) {
    return `${workflow?.title ?? "Your GIS workflow"} has been planned (${workflow?.workflow_id ?? "workflow ID pending"}). I need the following dataset input(s): ${missingInputs.join(", ")}. Enter the exact layer or dataset name in the Workflow panel. Nothing has been executed.`;
  }
  if (values.validation_result?.valid) {
    return `${workflow?.title ?? "Your GIS workflow"} has been planned and validated. Review the parameters in the Workflow panel, then explicitly approve or reject the handoff. Nothing has been executed.`;
  }
  return `Your request was submitted to the GeoSentinel workflow engine. Current state: ${values.overall_status ?? "unknown"}. Thread: ${threadId}. Review the Workflow panel for details.`;
}

export function GeoSentinelAssistant({ onWorkflowStarted }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Hello! I'm GeoSentinel AI. Describe the spatial analysis you need. I'll create a workflow plan, identify missing inputs and show validation results. GIS execution always remains behind your explicit approval.",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitRequest(requestText: string) {
    const userRequest = requestText.trim();
    if (!userRequest || submitting) return;

    setDraft("");
    setError(null);
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: userRequest },
    ]);
    setSubmitting(true);

    const threadId = createThreadId();
    try {
      await createWorkflow(userRequest, threadId);
      const snapshot = await getWorkflow(threadId);
      onWorkflowStarted(threadId, snapshot);
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", text: responseFor(snapshot, threadId) },
      ]);
    } catch (requestError) {
      const detail = requestError instanceof Error ? requestError.message : "Unknown backend error";
      setError(detail);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: "I couldn't submit that request to the GeoSentinel backend. Check the API connection and try again.",
        },
      ]);
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitRequest(draft);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (draft.trim() && !submitting) void submitRequest(draft);
    }
  }

  return (
    <section className="assistant-card" aria-label="GeoSentinel AI assistant">
      <div className="card-heading">
        <div>
          <p className="eyebrow">NATURAL-LANGUAGE GIS</p>
          <h2>GeoSentinel assistant</h2>
        </div>
        <span className="agent-badge">LANGGRAPH CONNECTED</span>
      </div>

      <div className="chat-panel" aria-live="polite" aria-label="Conversation">
        <div className="chat-brand">
          <div className="chat-avatar"><calcite-icon icon="globe" scale="m" /></div>
          <div>
            <strong>GeoSentinel AI</strong>
            <span>Controlled geospatial workflows</span>
          </div>
          <span className="chat-online-dot" title="Backend connection is monitored by the command center" />
        </div>

        <div className="chat-messages">
          {messages.map((message) => (
            <div className={`chat-message ${message.role}`} key={message.id}>
              <span className="message-role">{message.role === "assistant" ? "GEOSENTINEL" : "YOU"}</span>
              <p>{message.text}</p>
            </div>
          ))}
          {submitting && (
            <div className="chat-message assistant typing-message">
              <span className="message-role">GEOSENTINEL</span>
              <p>Planning your GIS workflow…</p>
            </div>
          )}
        </div>

        <div className="suggested-prompts" aria-label="Suggested GIS requests">
          <span>TRY A REQUEST</span>
          {SUGGESTED_PROMPTS.map((prompt) => (
            <button
              type="button"
              className="suggestion-chip"
              key={prompt}
              disabled={submitting}
              onClick={() => void submitRequest(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>

        <form className="chat-composer" onSubmit={handleSubmit}>
          <label className="visually-hidden" htmlFor="geosentinel-message">Describe your GIS analysis request</label>
          <textarea
            id="geosentinel-message"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder="Describe the spatial analysis you need…"
            rows={2}
            maxLength={4000}
            disabled={submitting}
          />
          <button className="send-button" type="submit" disabled={!draft.trim() || submitting} aria-label="Send GIS request">
            <calcite-icon icon="send" scale="m" />
          </button>
        </form>
        <div className="composer-hint">ENTER TO SEND · SHIFT + ENTER FOR NEW LINE · 4,000 CHARACTERS MAX</div>
      </div>

      {error && <p className="inline-error" role="alert">Backend request failed: {error}</p>}
      <p className="assistant-footnote">
        The assistant delegates planning to the existing Python LangGraph backend. It cannot approve workflows or execute ArcPy operations.
      </p>
    </section>
  );
}
