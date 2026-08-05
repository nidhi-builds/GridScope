/**
 * Plain-language legend. An operator should not need to know what "corridor" or
 * "inferred topology" means in the abstract — each row says what it implies for
 * the job in front of them.
 */
export function MapLegend() {
  return <aside className="map-legend" aria-label="Network map legend">
    <strong>What you are looking at</strong>
    <span className="legend-row"><i className="dot fault" aria-hidden="true" />
      <b>Fault location</b> — send the crew here</span>
    <span className="legend-row"><i className="dot pole" aria-hidden="true" />
      <b>Affected pole</b> — reported no power</span>
    <span className="legend-row"><i className="dot transformer" aria-hidden="true" />
      <b>Transformer</b> — feeds the poles below it</span>
    <span className="legend-row"><i className="line exact" aria-hidden="true" />
      <b>Exact span</b> — the fault is on this stretch of line</span>
    <span className="legend-row"><i className="line corridor" aria-hidden="true" />
      <b>Search corridor</b> — fault is somewhere along here, wiring unrecorded</span>
  </aside>;
}
