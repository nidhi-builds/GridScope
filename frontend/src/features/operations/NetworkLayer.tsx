import L from "leaflet";
import { GeoJSON } from "react-leaflet";
import type { FeatureCollection } from "../../api/types";

/**
 * Pole colours. These are the four facts an operator needs off the map, and the
 * distinction that matters most is grey vs hollow: a silent pole *should* be
 * reporting and is not, an uninstrumented pole has no sensor and never will.
 * Neither is evidence of an outage.
 */
export const POLE_STYLE: Record<string, { fill: string; stroke: string; opacity: number; radius: number }> = {
  confirmed_live: { fill: "#1f9e57", stroke: "#12703c", opacity: 0.85, radius: 3.5 },
  confirmed_dark: { fill: "#c32929", stroke: "#7d1414", opacity: 1, radius: 5 },
  unknown_silent: { fill: "#8792a4", stroke: "#5b687b", opacity: 0.8, radius: 3.5 },
  device_suspect: { fill: "#e0a030", stroke: "#8a5a00", opacity: 0.9, radius: 4 },
  uninstrumented: { fill: "#ffffff", stroke: "#aab4c4", opacity: 0.9, radius: 2.5 },
};

export const POLE_LABEL: Record<string, string> = {
  confirmed_live: "Has power",
  confirmed_dark: "No power — confirmed",
  unknown_silent: "Not reporting — unknown, not an outage",
  device_suspect: "Sensor unreliable",
  uninstrumented: "No sensor on this pole",
};

function poleLayer(feature: GeoJSON.Feature, latlng: L.LatLng): L.Layer {
  const properties = feature.properties as { asset?: string; state?: string; code?: string } | null;
  if (properties?.asset === "transformer") {
    return L.circleMarker(latlng, { radius: 5, color: "#12233f", weight: 2, fillColor: "#12233f", fillOpacity: 0.9 })
      .bindTooltip(`Transformer ${properties.code ?? ""}`.trim());
  }
  const style = POLE_STYLE[properties?.state ?? "uninstrumented"] ?? POLE_STYLE.uninstrumented;
  return L.circleMarker(latlng, {
    radius: style.radius, color: style.stroke, weight: 1,
    fillColor: style.fill, fillOpacity: style.opacity, opacity: style.opacity,
  }).bindTooltip(`${properties?.code ?? "Pole"} — ${POLE_LABEL[properties?.state ?? "uninstrumented"]}`);
}

const lineStyle = { color: "#9fb0c8", weight: 1.5, opacity: 0.65 };

/**
 * The base network, drawn under every incident overlay. Rendered on canvas
 * rather than SVG: a few thousand poles as individual DOM nodes makes panning
 * unusable.
 */
export function NetworkLayer({ network }: { network?: FeatureCollection }) {
  if (!network?.features.length) return null;
  return <GeoJSON
    key={`network-${network.features.length}`}
    data={network}
    style={() => lineStyle}
    pointToLayer={poleLayer}
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    {...({ renderer: L.canvas({ padding: 0.5 }) } as any)}
  />;
}
