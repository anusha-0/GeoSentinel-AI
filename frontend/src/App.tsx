import { useCallback, useEffect, useState } from "react";
import { getHealth } from "./services/api";
import type { ApiHealth, WorkflowCheckpoint } from "./types/workflow";
import { GeoSentinelAssistant } from "./components/GeoSentinelAssistant";
import { MapWorkspace } from "./components/MapWorkspace";
import { WorkflowInspector } from "./components/WorkflowInspector";

function createHealthLabel(health: ApiHealth | null, apiError: string | null) {
  if (health?.status === "healthy") return `API ${health.version}`;
  return apiError ? "API offline" : "Checking API";
}

export default function App() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<WorkflowCheckpoint | null>(null);
  const [activeSection, setActiveSection] = useState("command-center");

  const navigateTo = (section: string, elementId: string) => {
    setActiveSection(section);
    document.getElementById(elementId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const result = await getHealth();
        if (mounted) {
          setHealth(result);
          setApiError(null);
        }
      } catch (error) {
        if (mounted) {
          setHealth(null);
          setApiError(error instanceof Error ? error.message : "Backend unavailable");
        }
      }
    };
    void check();
    const interval = window.setInterval(check, 20_000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const handleWorkflowStarted = useCallback((newThreadId: string, newSnapshot: WorkflowCheckpoint) => {
    setThreadId(newThreadId);
    setSnapshot(newSnapshot);
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark"><calcite-icon icon="globe" scale="l" /></div>
          <div>
            <div className="brand-name">GeoSentinel <span>AI</span></div>
            <div className="brand-tagline">START IN INDIA. DESIGN FOR THE WORLD.</div>
          </div>
        </div>
        <div className="topbar-right">
          <div className={`connection-pill ${health?.status === "healthy" ? "connected" : "disconnected"}`}>
            <span className="status-dot" />{createHealthLabel(health, apiError)}
          </div>
          <div className="environment-label">DEVELOPMENT</div>
          <div className="user-avatar" aria-label="GeoSentinel workspace">GS</div>
        </div>
      </header>

      <div className="workspace-layout">
        <nav className="side-nav" aria-label="Main navigation">
          <button className={activeSection === "command-center" ? "nav-item active" : "nav-item"} onClick={() => navigateTo("command-center", "command-center")} title="Command center" aria-label="Command center">
            <calcite-icon icon="home" scale="m" />
          </button>
          <button className={activeSection === "map" ? "nav-item active" : "nav-item"} onClick={() => navigateTo("map", "map-workspace")} title="Map workspace" aria-label="Map workspace">
            <calcite-icon icon="map" scale="m" />
          </button>
          <button className={activeSection === "workflows" ? "nav-item active" : "nav-item"} onClick={() => navigateTo("workflows", "workflow-inspector")} title="Workflows" aria-label="Workflows">
            <calcite-icon icon="workflow" scale="m" />
          </button>
          <div className="nav-spacer" />
        </nav>

        <main className="main-content" id="command-center">
          <div className="page-heading">
            <div>
              <p className="eyebrow">GEOSPATIAL INTELLIGENCE PLATFORM</p>
              <h1>Command Center</h1>
              <p className="page-subtitle">Plan, review and verify spatial workflows from one operational workspace.</p>
            </div>
            <div className="date-stamp"><span className="status-dot status-dot-live" /> LIVE WORKSPACE</div>
          </div>

          <section className="overview-strip" aria-label="System overview">
            <div className="overview-card">
              <div className="overview-icon blue"><calcite-icon icon="server" /></div>
              <div><span>Backend service</span><strong>{health?.status === "healthy" ? "Healthy" : apiError ? "Unavailable" : "Checking…"}</strong></div>
              <span className={`mini-state ${health?.status === "healthy" ? "good" : "muted"}`} />
            </div>
            <div className="overview-card">
              <div className="overview-icon violet"><calcite-icon icon="workflow" /></div>
              <div><span>Current workflow</span><strong>{snapshot?.values?.overall_status?.replaceAll("_", " ") ?? "No active workflow"}</strong></div>
            </div>
            <div className="overview-card">
              <div className="overview-icon amber"><calcite-icon icon="play" /></div>
              <div><span>Execution</span><strong>{snapshot?.values?.execution_status ?? "Not started"}</strong></div>
            </div>
            <div className="overview-card">
              <div className="overview-icon green"><calcite-icon icon="check-circle" /></div>
              <div><span>Verification</span><strong>{snapshot?.values?.verification_status ?? "Not available"}</strong></div>
            </div>
          </section>

          <div className="content-grid">
            <div className="map-column">
              <MapWorkspace />
              <section className="guardrail-banner">
                <calcite-icon icon="shield-check" scale="m" />
                <div>
                  <strong>Controlled GIS execution</strong>
                  <span>Every operation requires validated inputs, explicit approval, ArcGIS Pro execution and independent verification.</span>
                </div>
              </section>
            </div>
            <aside className="right-column">
              <GeoSentinelAssistant onWorkflowStarted={handleWorkflowStarted} />
              <WorkflowInspector threadId={threadId} snapshot={snapshot} onSnapshotChange={setSnapshot} />
            </aside>
          </div>

          {apiError && (
            <div className="backend-warning" role="status">
              <calcite-icon icon="exclamation-mark-triangle" />
              <span>FastAPI is not reachable at the configured API proxy. Start the backend on port 8000. Details: {apiError}</span>
            </div>
          )}
        </main>
      </div>
      <footer className="app-footer">
        <span>GEOSENTINEL AI <span className="footer-divider">/</span> v0.9.5</span>
        <span>LangGraph orchestration · ArcGIS Pro execution boundary retained</span>
      </footer>
    </div>
  );
}
