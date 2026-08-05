import { GeoJSON, MapContainer, TileLayer } from "react-leaflet";
import type { FeatureCollection, IncidentSummary } from "../../api/types";
import { MapLegend } from "./MapLegend";
import "leaflet/dist/leaflet.css";

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
    <MapContainer center={center} zoom={13} scrollWheelZoom className="leaflet-map"><TileLayer attribution="© OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />{selectedGeometry && <GeoJSON data={selectedGeometry} style={{ color: "#c32929", weight: 5 }} />}</MapContainer><MapLegend />
  </section>;
}
