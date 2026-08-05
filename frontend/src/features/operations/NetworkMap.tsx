import L from "leaflet";
import { GeoJSON, MapContainer, TileLayer } from "react-leaflet";
import type { FeatureCollection, IncidentSummary } from "../../api/types";
import { MapLegend } from "./MapLegend";
import "leaflet/dist/leaflet.css";

/**
 * Scope incidents return one point per pole. Leaflet's default marker icon does
 * not resolve under Vite and would render hundreds of broken images, so points
 * are drawn as circles: transformers larger and darker than poles.
 */
function pointToLayer(feature: GeoJSON.Feature, latlng: L.LatLng): L.Layer {
  const transformer = (feature.properties as { asset?: string } | null)?.asset === "transformer";
  return L.circleMarker(latlng, {
    radius: transformer ? 6 : 3,
    color: transformer ? "#12233f" : "#c32929",
    weight: transformer ? 2 : 1,
    fillColor: transformer ? "#12233f" : "#c32929",
    fillOpacity: transformer ? 0.9 : 0.55,
  });
}

const fallbackCenter: [number, number] = [12.9716, 77.5946];

export function isGeometryForIncident(geometry: FeatureCollection | undefined, incidentId: string | undefined): boolean {
  return Boolean(incidentId && geometry?.features.length && geometry.features.every((feature) => (
    (feature.properties as { incident_id?: string } | null)?.incident_id === incidentId
  )));
}

export function NetworkMap({ incident, geometry }: { incident?: IncidentSummary; geometry?: FeatureCollection }) {
  const center: [number, number] = incident ? [incident.navigation.latitude, incident.navigation.longitude] : fallbackCenter;
  const selectedGeometry = isGeometryForIncident(geometry, incident?.id) ? geometry : undefined;
  return <section className="network-map" data-testid="network-map" data-selected={incident?.id ?? ""} aria-label="Selected incident map">
    <MapContainer center={center} zoom={13} scrollWheelZoom className="leaflet-map"><TileLayer attribution="© OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />{selectedGeometry && <GeoJSON key={incident?.id} data={selectedGeometry} style={{ color: "#c32929", weight: 5 }} pointToLayer={pointToLayer} />}</MapContainer><MapLegend />
  </section>;
}
