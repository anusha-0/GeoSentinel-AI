# GeoSentinel AI Frontend

React + TypeScript + Vite command-center application for GeoSentinel AI v0.9.5.

## Requirements

- Node.js 22.12 or later.
- npm 10 or later recommended.
- GeoSentinel FastAPI backend running at `http://127.0.0.1:8000`.
- An ArcGIS Location Platform or ArcGIS Online API key for secured basemap services.

## Setup

```powershell
cd D:\GeoSentinel-AI\frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development server proxies `/api/*` to `http://127.0.0.1:8000`. Override the target with `GEOSENTINEL_API_TARGET` if the backend uses another local address.

Set `VITE_ARCGIS_API_KEY` in `.env` to enable secured ArcGIS basemaps and services. Never commit a real key. Vite exposes `VITE_` variables to browser code, so treat this as a public API key: restrict its privileges and allowed referrers in ArcGIS Location Platform.

## Architecture boundary

- React owns the command-center interface, custom GeoSentinel chat, map workspace, workflow review and status presentation.
- ArcGIS Maps SDK for JavaScript owns browser mapping.
- Calcite Design System supplies Esri-aligned web components and styling.
- The custom React chat submits natural-language requests to the existing FastAPI workflow endpoints.
- Python LangGraph remains the authoritative planner and workflow orchestrator.
- The frontend does not approve workflows or execute GIS operations. Human approval remains a separate explicit action in the Workflow panel.
- ArcGIS Pro Python remains the only GIS execution runtime; FastAPI does not execute ArcPy.

## Current scope

- React + TypeScript + Vite command-center foundation.
- Calcite custom-elements integration.
- ArcGIS Map Components map workspace centered on India.
- Native React chat interface with suggested GIS requests, message history, loading and error states.
- FastAPI health, create, read, resolve, approve and synchronize calls.
- Workflow inspector for input resolution, explicit approval, ArcGIS Pro handoff and verification summary.

## Chat request lifecycle

1. The user enters a GIS request or selects a suggested prompt.
2. The browser creates a unique `GS-UI-*` thread ID and calls `POST /api/workflows`.
3. The browser reads the authoritative checkpoint using `GET /api/workflows/{thread_id}`.
4. The chat explains missing inputs or validation/approval state. The Workflow panel remains the place to resolve inputs and approve/reject.
5. ArcGIS Pro execution and independent verification remain outside the browser and are synchronized through the existing backend lifecycle endpoint.

The chat is an interface to the existing deterministic planner and LangGraph workflow. It does not currently call an LLM or invent GIS plans in the browser.
