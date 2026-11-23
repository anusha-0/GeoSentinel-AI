import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import esriConfig from "@arcgis/core/config.js";
import "@esri/calcite-components/main.css";
import "@esri/calcite-components/components/calcite-button";
import "@esri/calcite-components/components/calcite-chip";
import "@esri/calcite-components/components/calcite-icon";
import "@esri/calcite-components/components/calcite-notice";
import "@arcgis/map-components/components/arcgis-map";
import "@arcgis/map-components/components/arcgis-zoom";
import App from "./App";
import "./styles.css";

esriConfig.applicationName = "GeoSentinel AI";
const arcgisApiKey = import.meta.env.VITE_ARCGIS_API_KEY?.trim();
if (arcgisApiKey) {
  esriConfig.apiKey = arcgisApiKey;
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("GeoSentinel frontend root element was not found.");
}

document.documentElement.classList.add("calcite-mode-dark");

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
