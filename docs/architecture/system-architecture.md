# GeoSentinel AI - System Architecture

## 1. Overview

GeoSentinel AI is designed as a modular, agentic geospatial intelligence platform.

The system converts natural-language disaster-related requests into structured geospatial workflows.

## 2. Architectural Components

### Desktop Interface
- ArcGIS Pro 3.6
- ArcGIS Pro SDK for .NET
- C# and WPF
- WebView2
- React and TypeScript

### Agent Orchestration
- LangGraph
- Model-agnostic LLM integration
- Planning Agent
- Research Agent
- Spatial Analyst Agent
- Reporting Agent

### Geospatial Knowledge
- Hybrid RAG
- Qdrant
- GIS metadata catalog
- Research documents
- Dataset provenance

### GIS Execution
- Custom GIS MCP Server
- ArcPy processing worker
- Raster analysis
- Vector analysis
- Hydrological analysis
- Network analysis

### Backend
- Python
- FastAPI
- AG-UI integration

## 3. Execution Architecture

The AI orchestration layer and GIS execution layer will operate independently.

The agent will communicate with approved GIS tools through controlled interfaces.

ArcPy operations will execute in an ArcGIS Pro-compatible Python environment.

## 4. Human-in-the-Loop

The system will support:

1. Request understanding
2. Workflow planning
3. Evidence retrieval
4. User approval
5. GIS execution
6. Result inspection
7. Controlled revision
8. Evidence generation

## 5. Global Scalability

The architecture will avoid hardcoded geographical locations and country-specific assumptions.

Data providers, disaster workflows and geographical configurations will be modular.

## 6. Security and Reliability

- Validated GIS tool parameters
- Controlled execution permissions
- Source data protection
- Execution logging
- Dataset provenance
- Reproducible analysis
