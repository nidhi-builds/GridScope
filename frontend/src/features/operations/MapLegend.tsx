export function MapLegend() {
  return <aside className="map-legend" aria-label="Network map legend"><strong>Legend</strong><span className="live">Live</span><span className="dark">Dark</span><span className="unknown">Unknown / offline</span><span className="uninstrumented">Uninstrumented</span><span className="planned">Planned</span><span className="map-line registry">Registry topology</span><span className="map-line inferred">Inferred topology</span><span className="map-line selected-boundary">Selected boundary</span></aside>;
}
