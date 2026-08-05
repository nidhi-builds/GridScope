/**
 * Plain-language legend. An operator should not need to know what "corridor" or
 * "inferred topology" means in the abstract — each row says what it implies for
 * the job in front of them.
 *
 * Collapsible, because on a short map the expanded key covers the geography it
 * is meant to explain. Open by default: a key nobody finds is not a key.
 */
export function MapLegend() {
  return <details className="map-legend" open>
    <summary aria-label="Network map legend">Map key</summary>
    <span className="legend-row"><i className="dot fault" aria-hidden="true" />
      <b>Fault location</b><small>send the crew here</small></span>
    <span className="legend-row"><i className="dot pole" aria-hidden="true" />
      <b>Affected pole</b><small>reported no power</small></span>
    <span className="legend-row"><i className="dot transformer" aria-hidden="true" />
      <b>Transformer</b><small>feeds the poles below</small></span>
    <span className="legend-row"><i className="line exact" aria-hidden="true" />
      <b>Exact span</b><small>fault is on this stretch</small></span>
    <span className="legend-row"><i className="line corridor" aria-hidden="true" />
      <b>Search corridor</b><small>wiring unrecorded, search it</small></span>
  </details>;
}
