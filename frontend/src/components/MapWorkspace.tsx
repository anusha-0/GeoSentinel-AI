const hasArcgisApiKey = Boolean(import.meta.env.VITE_ARCGIS_API_KEY?.trim());

export function MapWorkspace() {
  return (
    <section className="map-card" id="map-workspace" aria-label="GIS map workspace">
      <div className="map-toolbar">
        <div>
          <p className="eyebrow">SPATIAL OPERATIONS</p>
          <h2>Map workspace</h2>
        </div>
        <div className="map-toolbar-actions">
          <span className="map-coordinate">India · 78.96°E, 20.59°N</span>
          <calcite-chip kind="neutral" scale="s">2D map</calcite-chip>
        </div>
      </div>
      <div className="map-frame">
        <arcgis-map
          id="geosentinel-map"
          basemap="dark-gray-vector"
          center="78.9629,20.5937"
          zoom="4"
          aria-label="ArcGIS map centred on India"
        >
          <arcgis-zoom slot="top-left" />
        </arcgis-map>
        {!hasArcgisApiKey && (
          <div className="map-credential-note">
            <calcite-icon icon="information" scale="s" />
            <span>Set VITE_ARCGIS_API_KEY to enable secured ArcGIS services and production basemaps.</span>
          </div>
        )}
        <div className="map-attribution">ArcGIS Maps SDK for JavaScript</div>
      </div>
      <div className="map-footer">
        <div className="map-footer-label"><span className="status-dot status-dot-muted" /> Layer catalog</div>
        <span className="muted-text">No web map layers connected yet</span>
      </div>
    </section>
  );
}
