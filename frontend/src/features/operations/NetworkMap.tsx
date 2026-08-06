import { useEffect, useMemo } from "react";
import L from "leaflet";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import type { FeatureCollection, IncidentSummary } from "../../api/types";
import { MapLegend } from "./MapLegend";
import "leaflet/dist/leaflet.css";

/**
 * Scope incidents return one point per pole. Leaflet's default marker icon does
 * not resolve under Vite and would render hundreds of broken images, so points
 * are drawn as circles: transformers larger and darker than poles.
 */
function pointToLayer(feature: GeoJSON.Feature, latlng: L.LatLng, selected: boolean): L.Layer {
  const properties = feature.properties as { asset?: string } | null;
  const transformer = properties?.asset === "transformer";
  // A boundary feature carries no `asset`: it is the fault point itself, and it
  // is the one thing on this map an operator is being asked to drive to.
  const fault = !properties?.asset;
  const radius = transformer ? 6 : fault ? (selected ? 9 : 7) : 3;
  const color = transformer ? "#12233f" : "#c32929";
  return L.circleMarker(latlng, {
    radius, color: fault ? "#7d1414" : color,
    weight: fault ? 3 : transformer ? 2 : 1,
    fillColor: color,
    fillOpacity: fault ? 0.95 : transformer ? 0.9 : 0.55,
    opacity: selected || fault ? 1 : 0.65,
  });
}

const fallbackCenter: [number, number] = [12.9716, 77.5946];

export function isGeometryForIncident(geometry: FeatureCollection | undefined, incidentId: string | undefined): boolean {
  return Boolean(incidentId && geometry?.features.length && geometry.features.every((feature) => (
    (feature.properties as { incident_id?: string } | null)?.incident_id === incidentId
  )));
}

/**
 * Selecting a ticket zooms to that incident; clearing the selection pulls back
 * to the whole queue. Keyed on `focusKey` so a re-poll that changes nothing does
 * not yank the viewport out from under someone mid-pan.
 */
function FitBounds({ collection, focusKey, fallback }: { collection?: FeatureCollection; focusKey: string; fallback?: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    if (!map || typeof map.flyToBounds !== "function") return;
    if (collection?.features.length) {
      const bounds = L.geoJSON(collection as never).getBounds();
      if (bounds.isValid()) {
        map.flyToBounds(bounds, { padding: [40, 40], maxZoom: 17, duration: 0.6 });
        return;
      }
    }
    // Geometry may be slow, empty or missing. Selecting a ticket must still move
    // the map, so fall back to the incident's own navigation point.
    if (fallback && typeof map.flyTo === "function") map.flyTo(fallback, 17, { duration: 0.6 });
    // Deliberately not keyed on `collection`: geometry arriving incident by
    // incident must not re-zoom five times while the operator is reading.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, focusKey, Boolean(collection?.features.length)]);
  return null;
}

export function NetworkMap({ incident, geometry, overview }: { incident?: IncidentSummary; geometry?: FeatureCollection; overview?: FeatureCollection }) {
  const center: [number, number] = incident ? [incident.navigation.latitude, incident.navigation.longitude] : fallbackCenter;
  const selectedGeometry = isGeometryForIncident(geometry, incident?.id) ? geometry : undefined;
  // The selected incident is drawn from its own fetch, so drop it from the
  // background layer rather than stacking two copies of the same line.
  const context = useMemo<FeatureCollection>(() => ({
    type: "FeatureCollection",
    features: (overview?.features ?? []).filter((feature) => (
      (feature.properties as { incident_id?: string } | null)?.incident_id !== incident?.id
    )),
  }), [overview, incident?.id]);
  const focus = selectedGeometry ?? (context.features.length ? context : undefined);
  const focusKey = incident?.id ?? `overview:${context.features.length}`;
  return <section className="network-map" data-testid="network-map" data-selected={incident?.id ?? ""} data-network-features={context.features.length} aria-label="Network map">
    <MapContainer center={center} zoom={13} scrollWheelZoom className="leaflet-map">
      <TileLayer attribution="© OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {context.features.length > 0 && <GeoJSON key={`context-${context.features.length}`} data={context} style={{ color: "#c32929", weight: 2, opacity: 0.5 }} pointToLayer={(feature, latlng) => pointToLayer(feature, latlng, false)} />}
      {selectedGeometry && <GeoJSON key={incident?.id} data={selectedGeometry} style={{ color: "#c32929", weight: 5 }} pointToLayer={(feature, latlng) => pointToLayer(feature, latlng, true)} />}
      <FitBounds collection={focus} focusKey={focusKey} fallback={incident ? [incident.navigation.latitude, incident.navigation.longitude] : undefined} />
    </MapContainer><MapLegend />
  </section>;
}
